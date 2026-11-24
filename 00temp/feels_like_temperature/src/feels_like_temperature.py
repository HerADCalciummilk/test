#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""体感温度计算。

本模块提供体感温度相关的计算工具，支持 ``xarray.DataArray`` 和
``numpy.ndarray`` 两种输入类型。模块包含两个主要能力：

- ``CalculateWindChill``：根据气温和 10 米风速计算风寒温度；
- ``calculate_feels_like_temperature``：综合风寒温度与显温，计算最终体感温度。

对于 ``xarray.DataArray`` 输入，必须在 ``attrs['units']`` 中提供单位；
对于 ``numpy.ndarray`` 输入，则按函数约定的默认单位进行计算。
输入单位字符串须为 ``cf_units`` 可识别的 CF 写法（如 ``degC``、``K``、``m s-1``、``km/h``、``Pa``、``hPa``、``%``、``1``）。

饱和水汽压辅助实现见 ``feels_like_temperature.src.utils._feels_like``。
"""

from __future__ import annotations

from typing import Union

from cf_units import Unit

import numpy as np
import xarray as xr

import meteva_base as meb

from feels_like_temperature.utils.base_plugin import BasePlugin
from feels_like_temperature.utils.utils import (
    convert_units,
    rebuild_to_meb_griddata,
)
from feels_like_temperature.src.util_plugin import (
    apparent_temperature as _calculate_apparent_temperature,
    feels_like_blend as _feels_like_temperature,
    wind_chill_celsius,
)
from feels_like_temperature.src.utils._feels_like import _prepare_meb_inputs

_MEB_VALID_VAL = (-np.inf, np.inf, np.nan)

__all__ = [
    "CalculateWindChill",
    "FeelsLikeTemperature",
    "calculate_feels_like_temperature",
]


class CalculateWindChill(BasePlugin):
    """计算风寒温度的插件类。

    该类用于根据气温和 10 米风速估算人体在寒冷多风环境下感受到的温度。
    既可以使用 ``process(...)``，也可以直接调用实例 ``plugin(...)``。
    """

    def _calculate_wind_chill(
        self,
        temperature: np.ndarray,
        wind_speed: np.ndarray,
    ) -> np.ndarray:
        """根据气温和风速计算风寒温度。

        参数
        ----------
        temperature : np.ndarray
            气温，单位为摄氏度。
        wind_speed : np.ndarray
            风速，单位为千米每小时。

        返回
        -------
        np.ndarray
            风寒温度，单位为摄氏度。
        """
        return wind_chill_celsius(temperature, wind_speed)

    def process(
        self,
        temperature_data: Union[xr.DataArray, np.ndarray],
        wind_speed_data: Union[xr.DataArray, np.ndarray],
        *,
        temperature_units: str = "degC",
        wind_speed_units: str = "m s-1",
    ) -> Union[xr.DataArray, np.ndarray]:
        """计算风寒温度。

        参数
        ----------
        temperature_data : xr.DataArray or np.ndarray
            气温数据。DataArray 必须提供 ``attrs['units']``；ndarray 使用
            ``temperature_units``。
        wind_speed_data : xr.DataArray or np.ndarray
            10 米风速数据。DataArray 必须提供 ``attrs['units']``；ndarray 使用
            ``wind_speed_units``。
        temperature_units : str, default="degC"
            ndarray 输入时的气温单位。
        wind_speed_units : str, default="m s-1"
            ndarray 输入时的风速单位。

        返回
        -------
        xr.DataArray or np.ndarray
            风寒温度，单位为摄氏度。
        """
        t_template = (
            meb.checkout_griddata(temperature_data, valid_val=_MEB_VALID_VAL)
            if isinstance(temperature_data, xr.DataArray)
            else None
        )
        w_template = (
            meb.checkout_griddata(wind_speed_data, valid_val=_MEB_VALID_VAL)
            if isinstance(wind_speed_data, xr.DataArray)
            else None
        )

        if t_template is not None and w_template is not None:
            if not meb.checkout_griddata_same_coords(
                [t_template, w_template], is_time_match=True
            ):
                raise ValueError("风速场与温度场的空间/时效坐标不一致")

        if isinstance(temperature_data, xr.DataArray):
            temp_degc = convert_units(temperature_data, "degC")
        else:
            temp_degc = np.asarray(temperature_data, dtype=np.float32)
            if temperature_units.strip() != "degC":
                temp_degc = Unit(temperature_units.strip()).convert(
                    temp_degc.astype(np.float64), Unit("degC")
                ).astype(np.float32)

        if isinstance(wind_speed_data, xr.DataArray):
            wind_kmh = convert_units(wind_speed_data, "km/h")
        else:
            wind_kmh = np.asarray(wind_speed_data, dtype=np.float32)
            if wind_speed_units.strip() != "km/h":
                wind_kmh = Unit(wind_speed_units.strip()).convert(
                    wind_kmh.astype(np.float64), Unit("km/h")
                ).astype(np.float32)

        wind_chill_data = self._calculate_wind_chill(temp_degc, wind_kmh)

        if t_template is not None:
            return rebuild_to_meb_griddata(
                wind_chill_data,
                template=t_template,
                name="wind_chill_temperature",
                units="degC",
            )
        return wind_chill_data


class FeelsLikeTemperature(BasePlugin):
    """综合显温与风寒温度，计算体感温度。"""

    def process(
        self,
        temperature: Union[xr.DataArray, np.ndarray],
        wind_speed: Union[xr.DataArray, np.ndarray],
        relative_humidity: Union[xr.DataArray, np.ndarray],
        pressure: Union[xr.DataArray, np.ndarray],
    ) -> Union[xr.DataArray, np.ndarray]:
        """计算体感温度。DataArray 须带单位；ndarray 默认 ℃、m/s、分数、Pa。"""
        t_template = _prepare_meb_inputs(temperature, wind_speed, relative_humidity, pressure)

        # 统一到 ℃、m/s、相对湿度分数、Pa
        t_celsius = (
            convert_units(temperature, "degC")
            if isinstance(temperature, xr.DataArray)
            else np.asarray(temperature, dtype=np.float32)
        )
        w_ms = (
            convert_units(wind_speed, "m s-1")
            if isinstance(wind_speed, xr.DataArray)
            else np.asarray(wind_speed, dtype=np.float32)
        )
        rh_frac = (
            convert_units(relative_humidity, "1")
            if isinstance(relative_humidity, xr.DataArray)
            else np.asarray(relative_humidity, dtype=np.float32)
        )
        p_pa = (
            convert_units(pressure, "Pa")
            if isinstance(pressure, xr.DataArray)
            else np.asarray(pressure, dtype=np.float32)
        )

        apparent = _calculate_apparent_temperature(t_celsius, w_ms, rh_frac, p_pa)
        wind_chill_result = CalculateWindChill().process(temperature, wind_speed)
        if isinstance(wind_chill_result, xr.DataArray):
            wind_chill = np.asarray(wind_chill_result.values, dtype=np.float32)
        else:
            wind_chill = np.asarray(wind_chill_result, dtype=np.float32)

        # 按气温区间融合风寒与显温
        feels_like_degc = _feels_like_temperature(t_celsius, apparent, wind_chill)

        if t_template is not None:
            output_units = str(t_template.attrs["units"]).strip()
        else:
            output_units = "degC"
        if output_units == "K":
            out_values = Unit("degC").convert(
                feels_like_degc.astype(np.float64), Unit("K")
            ).astype(np.float32)
        else:
            out_values = feels_like_degc.astype(np.float32)

        if t_template is not None:
            return rebuild_to_meb_griddata(
                out_values,
                template=t_template,
                name="feels_like_temperature",
                units=output_units,
            )
        return out_values


def calculate_feels_like_temperature(
    temperature: Union[xr.DataArray, np.ndarray],
    wind_speed: Union[xr.DataArray, np.ndarray],
    relative_humidity: Union[xr.DataArray, np.ndarray],
    pressure: Union[xr.DataArray, np.ndarray],
) -> Union[xr.DataArray, np.ndarray]:
    """计算体感温度。

    该函数综合显温和风寒温度，输出与输入形状一致的体感温度数组。

    单位处理约定如下：

    - ``temperature``：``degC`` 或 ``K``；
    - ``wind_speed``：``m s-1`` 或 ``km/h``；
    - ``relative_humidity``：``1``（分数）或 ``%``；
    - ``pressure``：``Pa``、``hPa`` 或 ``kPa``。
    以上单位字符串须为 ``cf_units`` 可识别的 CF 写法。

    对于 ``xarray.DataArray``，函数会先校验并规范化为标准六维网格，
    并检查各场与温度场的空间/时效坐标是否一致；
    对于 ``numpy.ndarray``，默认假定输入分别为摄氏度、米每秒、相对湿度分数和帕。

    参数
    ----------
    temperature : xr.DataArray or np.ndarray
        气温数据。
    wind_speed : xr.DataArray or np.ndarray
        10 米风速数据。
    relative_humidity : xr.DataArray or np.ndarray
        相对湿度数据。
    pressure : xr.DataArray or np.ndarray
        气压数据。

    返回
    -------
    xr.DataArray or np.ndarray
        若输入为 ``xarray.DataArray``，返回标准六维 ``xarray.DataArray``；
        若输入为 ``numpy.ndarray``，返回 ``numpy.ndarray``。
        输出温度单位与输入温度单位保持一致。
    """
    return FeelsLikeTemperature().process(
        temperature, wind_speed, relative_humidity, pressure
    )
