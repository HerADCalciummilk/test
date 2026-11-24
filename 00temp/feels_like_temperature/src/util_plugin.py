# -*- coding: utf-8 -*-
"""体感温度的纯计算步骤。文件读写与单位换算不在这里。"""
from __future__ import annotations

import numpy as np

from feels_like_temperature.src.utils._feels_like import (  # noqa: F401
    _calculate_svp_in_air,
    _svp_pure_water_goff_gratch,
)


def wind_chill_celsius(temperature: np.ndarray, wind_speed: np.ndarray) -> np.ndarray:
    """气温（℃）与风速（km/h）→ 风寒温度（℃）。"""
    # 4.824 km/h 为公式适用的最低有效风速
    eqn_component = np.clip(wind_speed, 4.824, None) ** 0.16
    return (
        13.12
        + 0.6215 * temperature
        - 11.37 * eqn_component
        + 0.3965 * temperature * eqn_component
    ).astype(np.float32)


def apparent_temperature(
    temperature: np.ndarray,
    wind_speed: np.ndarray,
    relative_humidity: np.ndarray,
    pressure: np.ndarray,
) -> np.ndarray:
    """显温。气温 ℃、风速 m/s、相对湿度 0–1、气压 Pa。"""
    t_kelvin = temperature + 273.15
    svp = _calculate_svp_in_air(t_kelvin, pressure)  # Pa
    # Steadman 回归式中水汽压单位为 hPa
    avp = 0.001 * svp * relative_humidity
    return (-2.7 + 1.04 * temperature + 2.0 * avp - 0.65 * wind_speed).astype(np.float32)


def feels_like_blend(
    temperature: np.ndarray,
    apparent_temperature_arr: np.ndarray,
    wind_chill: np.ndarray,
) -> np.ndarray:
    """低温取风寒，高温取显温，10–20℃ 线性过渡。"""
    feels_like_temperature = np.zeros(temperature.shape, dtype=np.float32)

    # 低温区：直接采用风寒温度
    feels_like_temperature[temperature < 10] = wind_chill[temperature < 10]

    # 过渡区（10–20℃）：按气温线性加权
    alpha = (temperature - 10.0) / 10.0
    temp_flt = alpha * apparent_temperature_arr + ((1 - alpha) * wind_chill)
    between = (temperature >= 10) & (temperature <= 20)
    feels_like_temperature[between] = temp_flt[between]

    # 高温区：直接采用显温
    feels_like_temperature[temperature > 20] = apparent_temperature_arr[temperature > 20]
    return feels_like_temperature
