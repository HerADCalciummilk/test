# -*- coding: utf-8 -*-
"""等压层场转换为等高层场。

插件入口是 ``PressureToHeightPlugin``。``read_pressure_levels`` 按路径逐个时次读取各等压层，
``stack_pressure_levels`` 只合并内存中的单层场。多个日期返回列表，不并进同一个数组。

垂直插值在位势高度上进行。温度、湿度、风分量使用线性插值；气压使用 ``vertical_interp="log"``。
默认目标为离地高度：目标海拔 = 地表海拔 + ``target_height``。夹不住目标海拔的气柱记为缺测。
风向由插值后的 U、V 经 ``wind_speed_and_direction`` 换算。

示例::

    from utils.pressure_to_height_plugin import (
        PressureToHeightPlugin,
        pressure_field_from_levels,
        read_pressure_levels,
        wind_speed_and_direction,
    )

    levels = (950, 925, 900, 850, 700, 500)
    times = ["2026083100", "2026083112"]
    temperatures = read_pressure_levels(tmp_template, times, levels, dt=3)
    heights = read_pressure_levels(hgt_template, times, levels, dt=3)
    u_winds = read_pressure_levels(u_template, times, levels, dt=3)
    v_winds = read_pressure_levels(v_template, times, levels, dt=3)
    linear = PressureToHeightPlugin(target_height=1000.0, height_type="agl", vertical_interp="linear")
    log_p = PressureToHeightPlugin(target_height=1000.0, height_type="agl", vertical_interp="log")

    for temperature, height, u_wind, v_wind in zip(temperatures, heights, u_winds, v_winds):
        temperature_h = linear(temperature, height, surface_altitude)
        pressure = pressure_field_from_levels(height, level_units="hPa", output_units="Pa")
        pressure_h = log_p(pressure, height, surface_altitude)
        speed, direction = wind_speed_and_direction(
            linear(u_wind, height, surface_altitude),
            linear(v_wind, height, surface_altitude),
        )
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Sequence, Tuple, Union

import numpy as np
import xarray as xr

from utils.base_plugin import BasePlugin

ArrayLike = Union[xr.DataArray, np.ndarray]

# 低于地表这一容差（米）的气压层视为地下层，不参与插值。
UNDERGROUND_TOLERANCE_M = 1.0

_LENGTH_TO_M = {
    "m": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "gpm": 1.0,
    "km": 1000.0,
    "ft": 0.3048,
}

_PRESSURE_TO_PA = {
    "pa": 1.0,
    "pascal": 1.0,
    "pascals": 1.0,
    "hpa": 100.0,
    "mbar": 100.0,
    "mb": 100.0,
    "kpa": 1000.0,
}


def _unit_key(units: str | None, default: str) -> str:
    text = (units or "").strip().lower()
    return text or default


def _pressure_to_pa(values: np.ndarray, units: str | None) -> np.ndarray:
    """把气压换算成 Pa。未写单位时按 hPa。"""
    key = _unit_key(units, "hpa")
    if key not in _PRESSURE_TO_PA:
        raise ValueError(f"无法把气压单位 {units!r} 换算成 Pa")
    return np.asarray(values, dtype=np.float64) * _PRESSURE_TO_PA[key]


def _lat_lon(data: xr.DataArray) -> Tuple[np.ndarray, np.ndarray]:
    if "lat" not in data.coords or "lon" not in data.coords:
        raise ValueError(f"{data.name or '输入场'} 必须包含 lat/lon 坐标")
    return (
        np.asarray(data.lat.values, dtype=np.float64),
        np.asarray(data.lon.values, dtype=np.float64),
    )


def _assert_same_horizontal(left: xr.DataArray, right: xr.DataArray, left_name: str, right_name: str) -> None:
    lat_l, lon_l = _lat_lon(left)
    lat_r, lon_r = _lat_lon(right)
    if (
        lat_l.shape != lat_r.shape
        or lon_l.shape != lon_r.shape
        or not np.allclose(lat_l, lat_r, rtol=0.0, atol=1e-3)
        or not np.allclose(lon_l, lon_r, rtol=0.0, atol=1e-3)
    ):
        raise ValueError(f"{left_name} 与 {right_name} 的水平网格不一致")


def stack_pressure_levels(
    fields: Sequence[xr.DataArray],
    *,
    level_units: str = "hPa",
) -> xr.DataArray:
    """把逐层单场沿 ``level`` 叠成一个等压层场。

    每一层应已带长度为 1 的 ``level`` 坐标（气压值）。各层水平网格必须一致。
    """
    if len(fields) < 2:
        raise ValueError("至少需要两层等压面才能做垂直插值")
    reference = fields[0]
    prepared = []
    for field in fields:
        if "level" not in field.dims:
            raise ValueError("每一层都必须带 level 维")
        if field.sizes["level"] != 1:
            raise ValueError("stack_pressure_levels 只接受单层场；多层场请直接交给插件")
        _assert_same_horizontal(reference, field, "基准层", "待叠层")
        prepared.append(field)
    stacked = xr.concat(prepared, dim="level")
    stacked.level.attrs["units"] = level_units
    attrs = dict(stacked.attrs)
    attrs["level_type"] = "isobaric"
    stacked.attrs = attrs
    return stacked


def _as_datetime(value) -> datetime:
    """接受 ``datetime`` 或 ``YYYYMMDDHH`` 字符串。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, np.datetime64):
        text = np.datetime_as_string(value, unit="s")
        return datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
    if isinstance(value, str):
        return datetime.strptime(value, "%Y%m%d%H")
    raise TypeError(f"time 需为 datetime 或 YYYYMMDDHH 字符串，实际为 {type(value).__name__}")


def _as_sequence(value):
    if isinstance(value, (str, datetime, np.datetime64)):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return [value]


def _forecast_pairs(time, dt) -> list[tuple[datetime, int]]:
    """把 time、dt 配成若干 (起报时间, 时效)。

    多个日期配同一个时效，或一个日期配多个时效。两者同时为列表时按位置配对。
    """
    times = [_as_datetime(item) for item in _as_sequence(time)]
    leads = [int(item) for item in _as_sequence(dt)]
    if len(times) == 1:
        return [(times[0], lead) for lead in leads]
    if len(leads) == 1:
        return [(item, leads[0]) for item in times]
    if len(times) == len(leads):
        return list(zip(times, leads))
    raise ValueError("time 与 dt 个数不一致：请使用多个日期配同一时效，或一个日期配多个时效")


def read_pressure_levels(
    path_template: str,
    time,
    levels: Sequence[float],
    *,
    dt: Union[int, Sequence[int]] = 0,
    level_units: str = "hPa",
) -> list[xr.DataArray]:
    """按路径模板逐个时次读取各等压层。

    每个时次单独叠成一个多层场，多个日期不会并进同一个数组。返回列表与时次顺序一致，
    逐项交给 ``PressureToHeightPlugin``。单个时次时列表长度为 1。

    ``path_template`` 用 ``{level}`` 表示气压层目录或文件名中的层次，其余时间记号交给
    ``meteva_base.get_path``：``YYYY``、``MM``、``DD``、``HH`` 来自 ``time``，``TTT`` 来自 ``dt``。

    ``time`` 可以是一个起报时间，或一组起报时间（``datetime`` 或 ``YYYYMMDDHH``）。
    ``dt`` 是时效（小时）。多个日期使用同一个时效；一个日期也可以配多个时效。
    任一层次文件不存在时抛出 ``FileNotFoundError``。
    """
    if "{level}" not in path_template:
        raise ValueError("path_template 需要包含 {level}，用于区分各等压层")
    if len(list(levels)) < 2:
        raise ValueError("至少需要两层等压面")

    import meteva_base as meb

    forecasts = []
    for when, lead in _forecast_pairs(time, dt):
        layers = []
        for level in levels:
            patterned = path_template.format(level=level)
            resolved = meb.get_path(patterned, when, dt=lead)
            if not resolved or not os.path.isfile(resolved):
                raise FileNotFoundError(
                    f"未找到等压层文件: level={level}, time={when:%Y%m%d%H}, dt={lead}, 路径={resolved or patterned}"
                )
            field = meb.read_griddata_from_nc(resolved)
            if "level" not in field.dims or field.sizes["level"] != 1:
                raise ValueError(f"文件不是单层场: {resolved}")
            field = field.assign_coords(level=[float(level)])
            layers.append(field)
        forecasts.append(stack_pressure_levels(layers, level_units=level_units))
    return forecasts


def pressure_field_from_levels(
    template: xr.DataArray,
    *,
    level_units: str | None = None,
    output_units: str = "Pa",
) -> xr.DataArray:
    """用气压层坐标构造各层恒定的气压场。

    没有逐层气压文件时，用 ``level`` 本身作为该层气压。返回值与 ``template``
    同形，数值在每一整层上为常数。
    """
    if "level" not in template.dims:
        raise ValueError("template 必须包含 level 维")
    units = level_units if level_units is not None else template.level.attrs.get("units")
    levels_pa = _pressure_to_pa(np.asarray(template.level.values), units)
    if _unit_key(output_units, "pa") == "pa":
        levels_out = levels_pa
        out_units = "Pa"
    elif _unit_key(output_units, "pa") == "hpa":
        levels_out = levels_pa / 100.0
        out_units = "hPa"
    else:
        raise ValueError(f"output_units 仅支持 Pa 或 hPa，实际为 {output_units!r}")

    level_axis = template.dims.index("level")
    reshape = [1] * template.ndim
    reshape[level_axis] = levels_out.size
    values = np.broadcast_to(levels_out.reshape(reshape), template.shape).copy()
    out = template.copy(data=values.astype(np.float32))
    out.name = "air_pressure"
    attrs = dict(template.attrs)
    attrs["units"] = out_units
    attrs["level_type"] = "isobaric"
    out.attrs = attrs
    return out


def wind_speed_and_direction(u_wind: ArrayLike, v_wind: ArrayLike) -> Tuple[ArrayLike, ArrayLike]:
    """由网格 U/V 计算风速和气象风向。

    风向为相对真北的来向，单位度，顺时针。U 向东为正，V 向北为正。
    输入为 ``DataArray`` 时返回同坐标的两个场；否则返回 ndarray。
    """
    if isinstance(u_wind, xr.DataArray) != isinstance(v_wind, xr.DataArray):
        raise ValueError("u_wind 与 v_wind 必须同为 DataArray 或同为 ndarray")
    u_values = np.asarray(u_wind.values if isinstance(u_wind, xr.DataArray) else u_wind, dtype=np.float64)
    v_values = np.asarray(v_wind.values if isinstance(v_wind, xr.DataArray) else v_wind, dtype=np.float64)
    if u_values.shape != v_values.shape:
        raise ValueError("u_wind 与 v_wind 的形状不一致")
    speed = np.hypot(u_values, v_values)
    direction = (np.degrees(np.arctan2(-u_values, -v_values)) + 360.0) % 360.0
    direction = np.where(np.isfinite(speed), direction, np.nan)
    if not isinstance(u_wind, xr.DataArray):
        return speed, direction

    speed_da = u_wind.copy(data=speed.astype(np.float32))
    speed_da.name = "wind_speed"
    speed_attrs = dict(u_wind.attrs)
    speed_attrs["units"] = "m s-1"
    speed_da.attrs = speed_attrs

    direction_da = u_wind.copy(data=direction.astype(np.float32))
    direction_da.name = "wind_from_direction"
    direction_attrs = dict(u_wind.attrs)
    direction_attrs["units"] = "degrees"
    direction_da.attrs = direction_attrs
    return speed_da, direction_da


class PressureToHeightPlugin(BasePlugin):
    """把已叠好的等压层要素插到单一目标高度。

    调用 ``plugin(field, geopotential_height, surface_altitude)`` 即执行 :meth:`process`。
    目标高度和插值方式在构造时固定，同一实例可反复用于温度、湿度、风分量和气压。
    """

    def __init__(
        self,
        target_height: float = 1000.0,
        height_units: str = "m",
        height_type: str = "agl",
        vertical_interp: str = "linear",
    ):
        """指定目标高度和插值方式。

        参数
        ----------
        target_height : float, 默认 1000.0
            目标高度。``height_type="agl"`` 时表示离地高度，``"amsl"`` 时表示海拔。
        height_units : str, 默认 ``"m"``
            ``target_height`` 的单位，支持 ``m``、``km``、``ft``。输出 ``level`` 使用同一单位和数值。
        height_type : str, 默认 ``"agl"``
            ``agl``：目标海拔 = 地表海拔 + 目标高度。``amsl``：所有格点插到同一海拔。
        vertical_interp : str, 默认 ``"linear"``
            ``linear`` 沿位势高度线性插值，用于温度、湿度和风分量。
            ``log`` 对正值取对数后插值再还原，用于气压。
        """
        self.target_height = target_height
        self.height_units = height_units
        self.height_type = height_type
        self.vertical_interp = vertical_interp

    @staticmethod
    def _length_to_metres(values: np.ndarray, units: str | None, *, default: str = "m") -> np.ndarray:
        """把长度或位势高度换算成米。缺省单位按 ``default``。"""
        key = _unit_key(units, default)
        if key not in _LENGTH_TO_M:
            raise ValueError(f"无法把长度单位 {units!r} 换算成米")
        return np.asarray(values, dtype=np.float64) * _LENGTH_TO_M[key]

    @staticmethod
    def _surface_2d(surface: xr.DataArray) -> xr.DataArray:
        """把地表海拔收成 (lat, lon)。仅允许额外维度长度为 1。"""
        if "lat" not in surface.dims or "lon" not in surface.dims:
            raise ValueError("surface_altitude 必须包含 lat/lon 维")
        extra = [dim for dim in surface.dims if dim not in ("lat", "lon")]
        squeezed = surface
        for dim in extra:
            if squeezed.sizes[dim] != 1:
                raise ValueError(f"surface_altitude 的 {dim} 维长度必须为 1，实际为 {squeezed.sizes[dim]}")
            squeezed = squeezed.isel({dim: 0}, drop=True)
        return squeezed.transpose("lat", "lon")

    @staticmethod
    def _interp_columns(heights_m: np.ndarray, values: np.ndarray, target_m: np.ndarray, *, log: bool) -> np.ndarray:
        """沿高度把每一列插到目标海拔。地下层应为 NaN。"""
        valid_height = np.isfinite(heights_m)
        height_for_sort = np.where(valid_height, heights_m, np.inf)
        order = np.argsort(height_for_sort, axis=0)
        height_sorted = np.take_along_axis(heights_m, order, axis=0)
        value_sorted = np.take_along_axis(values, order, axis=0)
        height_sorted = np.where(np.isfinite(height_sorted), height_sorted, np.nan)
        if log:
            value_sorted = np.where(np.isfinite(value_sorted) & (value_sorted > 0.0), value_sorted, np.nan)
            value_sorted = np.log(value_sorted)

        out = np.full(target_m.shape, np.nan, dtype=np.float64)
        n_levels = height_sorted.shape[0]
        if n_levels < 2:
            return out
        for index in range(n_levels - 1):
            z0 = height_sorted[index]
            z1 = height_sorted[index + 1]
            f0 = value_sorted[index]
            f1 = value_sorted[index + 1]
            ok = (
                np.isfinite(target_m)
                & np.isfinite(z0)
                & np.isfinite(z1)
                & np.isfinite(f0)
                & np.isfinite(f1)
                & (z1 > z0)
                & (target_m >= z0)
                & (target_m <= z1)
            )
            if not np.any(ok):
                continue
            weight = np.zeros_like(target_m)
            weight[ok] = (target_m[ok] - z0[ok]) / (z1[ok] - z0[ok])
            interpolated = f0[ok] * (1.0 - weight[ok]) + f1[ok] * weight[ok]
            if log:
                interpolated = np.exp(interpolated)
            out[ok] = interpolated
        return out

    def process(
        self,
        field: xr.DataArray,
        geopotential_height: xr.DataArray,
        surface_altitude: xr.DataArray,
    ) -> xr.DataArray:
        """把一个时次的等压层要素插到构造时指定的目标高度。

        参数
        ----------
        field : xr.DataArray
            等压层要素，至少两层。``level`` 为气压，须与 ``geopotential_height`` 的层次一致。
            水平网格也须一致。
        geopotential_height : xr.DataArray
            同位势高度，形状和 ``level`` 与 ``field`` 相同。数值单位为 ``m`` 或 ``gpm``，
            写在 ``attrs["units"]`` 中；缺省按米。
        surface_altitude : xr.DataArray
            地表海拔，单位 ``m``。可以是 ``(lat, lon)``，也可以是其余维长度均为 1 的多维场。
            经纬须与 ``field`` 一致。

        返回值
        -------
        xr.DataArray
            单层结果。``level`` 等于 ``target_height``，``level.attrs["units"]`` 为
            ``height_units``，``attrs["level_type"]`` 为 ``"height"``。
            低于地表的气压层不参与插值。目标海拔落在整柱有效高度之外时，该格点为 NaN。
        """
        if "level" not in field.dims or "level" not in geopotential_height.dims:
            raise ValueError("field 与 geopotential_height 都必须包含 level 维")
        if field.sizes["level"] < 2:
            raise ValueError("垂直插值至少需要两层")
        if tuple(field.sizes.values()) != tuple(geopotential_height.sizes.values()) or field.dims != geopotential_height.dims:
            raise ValueError("field 与 geopotential_height 的维度不一致")
        if not np.allclose(
            np.asarray(field.level.values, dtype=np.float64),
            np.asarray(geopotential_height.level.values, dtype=np.float64),
            rtol=0.0,
            atol=1e-3,
        ):
            raise ValueError("field 与 geopotential_height 的气压层坐标不一致")

        mode = self.height_type.strip().lower()
        if mode not in ("agl", "amsl"):
            raise ValueError(f"height_type 仅支持 agl 或 amsl，实际为 {self.height_type!r}")
        interp = self.vertical_interp.strip().lower()
        if interp not in ("linear", "log"):
            raise ValueError(f"vertical_interp 仅支持 linear 或 log，实际为 {self.vertical_interp!r}")

        _assert_same_horizontal(field, geopotential_height, "field", "geopotential_height")
        surface = self._surface_2d(surface_altitude)
        _assert_same_horizontal(field, surface, "field", "surface_altitude")

        target_m = float(self._length_to_metres(np.array(self.target_height), self.height_units))
        level_axis = field.dims.index("level")
        heights = self._length_to_metres(
            np.asarray(geopotential_height.values, dtype=np.float64),
            geopotential_height.attrs.get("units"),
            default="m",
        )
        values = np.asarray(field.values, dtype=np.float64)
        heights = np.moveaxis(heights, level_axis, 0)
        values = np.moveaxis(values, level_axis, 0)

        surface_m = self._length_to_metres(
            np.asarray(surface.values, dtype=np.float64),
            surface.attrs.get("units"),
            default="m",
        )
        rest_shape = heights.shape[1:]
        if rest_shape[-2:] != surface_m.shape:
            raise ValueError("surface_altitude 的经纬尺寸与要素场不一致")
        surface_broadcast = np.broadcast_to(surface_m, rest_shape)
        heights = np.where(heights >= surface_broadcast[None, ...] - UNDERGROUND_TOLERANCE_M, heights, np.nan)
        if mode == "agl":
            target = surface_broadcast + target_m
        else:
            target = np.full(rest_shape, target_m, dtype=np.float64)

        n_column = int(np.prod(rest_shape, dtype=np.int64))
        interpolated = self._interp_columns(
            heights.reshape(heights.shape[0], n_column),
            values.reshape(values.shape[0], n_column),
            np.reshape(target, n_column),
            log=(interp == "log"),
        )
        restored = np.expand_dims(interpolated.reshape(rest_shape), axis=level_axis)

        out = field.isel(level=[0]).copy(data=restored.astype(np.float32))
        out = out.assign_coords(level=np.array([self.target_height], dtype=np.float32))
        out.level.attrs["units"] = self.height_units
        attrs = dict(field.attrs)
        attrs["level_type"] = "height"
        attrs["height_type"] = mode
        attrs["vertical_interp"] = interp
        attrs["target_height"] = float(self.target_height)
        attrs["target_height_units"] = self.height_units
        out.attrs = attrs
        return out
