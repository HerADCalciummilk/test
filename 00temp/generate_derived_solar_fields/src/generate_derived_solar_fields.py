#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""太阳衍生辅助场生成算法。"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Sequence, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray

from generate_derived_solar_fields.utils.base_plugin import BasePlugin
from generate_derived_solar_fields.src.utils.solar import (
    DAYS_IN_YEAR,
    MINUTES_IN_HOUR,
    SECONDS_IN_MINUTE,
    calc_solar_elevation,
    calc_solar_time,
    get_day_of_year,
    get_hour_of_day,
)
from generate_derived_solar_fields.src.utils.grid_mapping import extract_lat_lon_mesh

DEFAULT_TEMPORAL_SPACING_IN_MINUTES = 30

SOLAR_TIME_CF_NAME = "local_solar_time"
CLEARSKY_SOLAR_RADIATION_CF_NAME = (
    "integral_of_surface_downwelling_shortwave_flux_in_air_assuming_clear_sky_wrt_time"
)

__all__ = [
    "GenerateSolarTime",
    "GenerateClearskySolarRadiation",
]


class GenerateSolarTime(BasePlugin):
    """
    地方太阳时插件。

    功能逻辑：
    - 对输入 `target_grid` 做六维单场校验；
    - 提取网格经纬坐标（若是投影坐标则先转换为经纬）；
    - 结合传入时刻计算每个格点的地方太阳时（0-24 小时）；
    - 将二维结果按模板回填为六维 `xr.DataArray` 输出，并写入标准属性。
    """

    def __repr__(self) -> str:
        return "<GenerateSolarTime>"

    def process(
        self,
        target_grid: xr.DataArray,
        time: datetime,
        new_title: str | None = None,
    ) -> xr.DataArray:
        """
        在目标网格上计算地方太阳时。

        参数：
        - target_grid: 目标网格，要求为 `member, level, time, dtime, lat, lon` 六维单场。
        - time: 计算时刻（`datetime`）。
        - new_title: 可选标题；若为 `None`，则移除输出中的 `title`。

        返回：
        - `xr.DataArray`：与 `target_grid` 同维度结构的地方太阳时结果，
          变量名为 `local_solar_time`，单位为 `hours`。
        """
        target_grid = meb.checkout_griddata(
            target_grid, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
        )
        if not isinstance(time, datetime):
            raise TypeError("time 必须为 datetime。")
        valid_time = time
        _, lons_2d = extract_lat_lon_mesh(target_grid)
        day_of_year = get_day_of_year(valid_time)
        utc_hour = get_hour_of_day(valid_time)
        solar_time_data_2d = calc_solar_time(lons_2d, day_of_year, utc_hour, normalise=True)
        # 二维结果扩成六维：先占位 (1,1,1,1,lat,lon)，再广播到模板形状
        target_shape = tuple(target_grid.sizes[dim] for dim in target_grid.dims)
        values = np.broadcast_to(
            np.asarray(solar_time_data_2d, dtype=np.float32).reshape(
                1, 1, 1, 1, solar_time_data_2d.shape[0], solar_time_data_2d.shape[1]
            ),
            target_shape,
        ).copy()

        result = xr.DataArray(
            values.astype(np.float32),
            dims=target_grid.dims,
            coords=target_grid.coords,
            attrs=dict(target_grid.attrs),
            name=SOLAR_TIME_CF_NAME,
        )
        if result.sizes.get("time", 0) == 1:
            result = result.assign_coords(
                time=("time", np.array([np.datetime64(valid_time)], dtype="datetime64[ns]"))
            )
        result.attrs["units"] = "hours"
        if new_title is not None:
            result.attrs["title"] = new_title
        else:
            result.attrs.pop("title", None)
        return result


class GenerateClearskySolarRadiation(BasePlugin):
    """
    晴空太阳辐射累计插件。

    功能逻辑：
    - 对目标网格做六维单场校验；
    - 统一并校验可选输入（海拔、Linke 浑浊度）与目标网格空间一致性；
    - 按累积窗口生成时间序列，逐时刻计算晴空辐照度；
    - 沿时间维积分得到累计辐射，并封装为六维 `xr.DataArray` 返回。
    """

    def __repr__(self) -> str:
        return "<GenerateClearskySolarRadiation>"

    @staticmethod
    def _prepare_optional_inputs(
        target_grid: xr.DataArray,
        surface_altitude: xr.DataArray | None,
        linke_turbidity: xr.DataArray | None,
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """补齐可选输入并确保网格一致。"""
        if surface_altitude is None:
            surface_altitude = target_grid.copy(deep=True)
            surface_altitude.values = np.zeros_like(target_grid.values, dtype=np.float32)
            surface_altitude.name = "surface_altitude"
            surface_altitude.attrs = dict(surface_altitude.attrs)
            surface_altitude.attrs["units"] = "m"
        else:
            surface_altitude = meb.checkout_griddata(
                surface_altitude, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
            )
            if not np.array_equal(surface_altitude.coords["lat"].values, target_grid.coords["lat"].values) or not np.array_equal(
                surface_altitude.coords["lon"].values, target_grid.coords["lon"].values
            ):
                raise ValueError("surface altitude spatial coordinates do not match target_grid")

        if linke_turbidity is None:
            linke_turbidity = target_grid.copy(deep=True)
            linke_turbidity.values = 3.0 * np.ones_like(target_grid.values, dtype=np.float32)
            linke_turbidity.name = "linke_turbidity"
            linke_turbidity.attrs = dict(linke_turbidity.attrs)
            linke_turbidity.attrs["units"] = "1"
        else:
            linke_turbidity = meb.checkout_griddata(
                linke_turbidity, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
            )
            if not np.array_equal(linke_turbidity.coords["lat"].values, target_grid.coords["lat"].values) or not np.array_equal(
                linke_turbidity.coords["lon"].values, target_grid.coords["lon"].values
            ):
                raise ValueError("linke-turbidity spatial coordinates do not match target_grid")

        return surface_altitude, linke_turbidity

    @staticmethod
    def _irradiance_times(
        time: datetime, accumulation_period: int, temporal_spacing: int
    ) -> list[datetime]:
        """获取积分时刻序列。"""
        if accumulation_period * MINUTES_IN_HOUR % temporal_spacing != 0:
            raise ValueError(
                f"accumulation_period in minutes ({accumulation_period} * 60) must be integer multiple of temporal_spacing ({temporal_spacing})."
            )
        accumulation_start_time = time - timedelta(hours=accumulation_period)
        time_step = timedelta(minutes=temporal_spacing)
        n_time_steps = timedelta(hours=accumulation_period) // timedelta(minutes=temporal_spacing)
        return [accumulation_start_time + step * time_step for step in range(n_time_steps + 1)]

    @staticmethod
    def _calc_optical_air_mass(zenith: ndarray) -> ndarray:
        """计算相对光学气团质量。"""
        zenith_above_horizon = np.where(np.abs(zenith) >= 90, np.nan, zenith)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", "invalid value encountered in power")
            optical_air_mass = 1.0 / (
                np.cos(np.radians(zenith_above_horizon))
                + 0.50572 * (96.07995 - zenith_above_horizon) ** (-1.6364)
            )
        return np.nan_to_num(optical_air_mass)

    def _calc_clearsky_ineichen(
        self,
        zenith_angle: ndarray,
        day_of_year: int,
        surface_altitude: Union[ndarray, float],
        linke_turbidity: Union[ndarray, float],
    ) -> ndarray:
        """按 Ineichen-Perez 公式计算晴空全球水平辐照。"""
        theta0 = 2 * np.pi * day_of_year / DAYS_IN_YEAR
        extra_terrestrial_irradiance = 1367.7 * (1 + 0.033 * np.cos(theta0))
        optical_air_mass = self._calc_optical_air_mass(zenith_angle)
        fh1 = np.exp(-1.0 * surface_altitude / 8000.0)
        fh2 = np.exp(-1.0 * surface_altitude / 1250.0)
        cg1 = 0.0000509 * surface_altitude + 0.868
        cg2 = 0.0000392 * surface_altitude + 0.0387
        cos_zenith = np.maximum(np.cos(np.radians(zenith_angle)), 0)
        ghi = (
            cg1
            * extra_terrestrial_irradiance
            * cos_zenith
            * np.exp(-1.0 * cg2 * optical_air_mass * (fh1 + fh2 * (linke_turbidity - 1)))
        )
        return np.minimum(ghi, extra_terrestrial_irradiance)

    def _calc_clearsky_solar_radiation_data(
        self,
        target_grid: xr.DataArray,
        irradiance_times: Sequence[datetime],
        surface_altitude_2d: ndarray,
        linke_turbidity_2d: ndarray,
        temporal_spacing: int,
    ) -> ndarray:
        """计算给定时段累计晴空辐射二维场。"""
        lats_2d, lons_2d = extract_lat_lon_mesh(target_grid)
        irradiance_data = np.zeros(
            shape=(len(irradiance_times), lats_2d.shape[0], lats_2d.shape[1]),
            dtype=np.float32,
        )
        for time_index, time_step in enumerate(irradiance_times):
            day_of_year = get_day_of_year(time_step)
            utc_hour = get_hour_of_day(time_step)
            zenith_angle = 90.0 - calc_solar_elevation(lats_2d, lons_2d, day_of_year, utc_hour)
            irradiance_data[time_index, :, :] = self._calc_clearsky_ineichen(
                zenith_angle,
                day_of_year,
                surface_altitude=surface_altitude_2d,
                linke_turbidity=linke_turbidity_2d,
            )
        return np.trapezoid(
            irradiance_data, dx=SECONDS_IN_MINUTE * temporal_spacing, axis=0
        ).astype(np.float32)

    def process(
        self,
        target_grid: xr.DataArray,
        time: datetime,
        accumulation_period: int,
        surface_altitude: xr.DataArray | None = None,
        linke_turbidity: xr.DataArray | None = None,
        temporal_spacing: int = DEFAULT_TEMPORAL_SPACING_IN_MINUTES,
        new_title: str | None = None,
    ) -> xr.DataArray:
        """
        计算指定时段内的累计晴空太阳辐射。

        参数：
        - target_grid: 目标网格，要求为 `member, level, time, dtime, lat, lon` 六维单场。
        - time: 累积结束时刻（`datetime`）。
        - accumulation_period: 累积时长（小时）。
        - surface_altitude: 可选海拔场；不传时使用全 0 默认海拔场。
        - linke_turbidity: 可选 Linke 浑浊度场；不传时使用默认值 3.0。
        - temporal_spacing: 积分时间步长（分钟），默认 30。
        - new_title: 可选标题；若为 `None`，则移除输出中的 `title`。

        返回：
        - `xr.DataArray`：与 `target_grid` 同维度结构的累计晴空辐射结果，
          变量名为
          `integral_of_surface_downwelling_shortwave_flux_in_air_assuming_clear_sky_wrt_time`，
          单位为 `W s m-2`，并附带时间上下界与积分相关属性。
        """
        target_grid = meb.checkout_griddata(
            target_grid, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
        )
        if not isinstance(time, datetime):
            raise TypeError("time 必须为 datetime。")
        valid_time = time
        surface_altitude, linke_turbidity = self._prepare_optional_inputs(
            target_grid, surface_altitude, linke_turbidity
        )
        at_mean_sea_level = np.allclose(surface_altitude.values, 0.0)
        irradiance_times = self._irradiance_times(
            valid_time, accumulation_period, temporal_spacing
        )

        surface_altitude_2d = np.asarray(surface_altitude.values.squeeze(), dtype=np.float32)
        linke_turbidity_2d = np.asarray(linke_turbidity.values.squeeze(), dtype=np.float32)
        solar_radiation_2d = self._calc_clearsky_solar_radiation_data(
            target_grid,
            irradiance_times,
            surface_altitude_2d,
            linke_turbidity_2d,
            temporal_spacing,
        )
        # 二维结果扩成六维：先占位 (1,1,1,1,lat,lon)，再广播到模板形状
        target_shape = tuple(target_grid.sizes[dim] for dim in target_grid.dims)
        values = np.broadcast_to(
            np.asarray(solar_radiation_2d, dtype=np.float32).reshape(
                1, 1, 1, 1, solar_radiation_2d.shape[0], solar_radiation_2d.shape[1]
            ),
            target_shape,
        ).copy()

        result = xr.DataArray(
            values.astype(np.float32),
            dims=target_grid.dims,
            coords=target_grid.coords,
            attrs=dict(target_grid.attrs),
            name=CLEARSKY_SOLAR_RADIATION_CF_NAME,
        )
        if result.sizes.get("time", 0) == 1:
            accumulation_start = valid_time - timedelta(hours=accumulation_period)
            time_lower = np.datetime64(accumulation_start, "ns")
            time_upper = np.datetime64(valid_time, "ns")
            result = result.assign_coords(
                time=("time", np.array([time_upper], dtype="datetime64[ns]"))
            )
            result = result.assign_coords(
                time_lower_bound=("time", np.array([time_lower], dtype="datetime64[ns]")),
                time_upper_bound=("time", np.array([time_upper], dtype="datetime64[ns]")),
            )
            result.coords["time"].attrs["bounds"] = "time_lower_bound time_upper_bound"
        result.attrs["units"] = "W s m-2"
        result.attrs["vertical_coordinate"] = "altitude" if at_mean_sea_level else "height"
        result.attrs["accumulation_period_hours"] = int(accumulation_period)
        result.attrs["temporal_spacing_minutes"] = int(temporal_spacing)
        if new_title is not None:
            result.attrs["title"] = new_title
        else:
            result.attrs.pop("title", None)
        return result


