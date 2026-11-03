#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""查找太阳相对位置的工具。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Union

import numpy as np
from numpy import ndarray

# 时间常数
HOURS_IN_DAY = 24
DAYS_IN_YEAR = 365
MINUTES_IN_HOUR = 60
SECONDS_IN_MINUTE = 60

__all__ = [
    "DAYS_IN_YEAR",
    "MINUTES_IN_HOUR",
    "SECONDS_IN_MINUTE",
    "get_day_of_year",
    "get_hour_of_day",
    "calc_solar_declination",
    "calc_solar_time",
    "calc_solar_hour_angle",
    "calc_solar_elevation",
]


def get_day_of_year(time: datetime) -> int:
    """获取一年中的第几天（从 0 开始）。"""
    return time.timetuple().tm_yday - 1


def get_hour_of_day(time: datetime) -> float:
    """获取 UTC 小时，分钟以小时小数表示，秒按四舍五入到分钟。"""
    # 通过将秒数部分添加到时间来将时间四舍五入到最近的分钟
    rounded_time = time + timedelta(seconds=time.second)
    # 避免时间四舍五入后进入下一天的情况
    if rounded_time.day != time.day:
        return float(HOURS_IN_DAY)
    return (rounded_time.hour * MINUTES_IN_HOUR + rounded_time.minute) / MINUTES_IN_HOUR


def calc_solar_declination(day_of_year: int) -> float:
    """计算太阳赤纬角（度）。"""
    if day_of_year < 0 or day_of_year > DAYS_IN_YEAR:
        raise ValueError("Day of the year must be between 0 and 365")
    return -23.5 * np.cos(np.radians(0.9856 * day_of_year + 9.3))


def calc_solar_time(
    longitudes: Union[float, ndarray],
    day_of_year: int,
    utc_hour: float,
    normalise: bool = False,
) -> Union[float, ndarray]:
    """根据经度计算地方太阳时（小时）。"""
    if day_of_year < 0 or day_of_year > DAYS_IN_YEAR:
        raise ValueError("Day of the year must be between 0 and 365")
    if utc_hour < 0.0 or utc_hour > 24.0:
        raise ValueError("Hour must be between 0 and 24.0")
    theta0 = 2 * np.pi * day_of_year / DAYS_IN_YEAR
    eqt = (
        0.000075
        + 0.001868 * np.cos(theta0)
        - 0.032077 * np.sin(theta0)
        - 0.014615 * np.cos(2 * theta0)
        - 0.040849 * np.sin(2 * theta0)
    )
    lon_correction = 24.0 * np.asarray(longitudes) / 360.0
    solar_time = utc_hour + lon_correction + eqt * 12 / np.pi
    if normalise:
        solar_time = solar_time % 24
    return solar_time


def calc_solar_hour_angle(
    longitudes: Union[float, ndarray], day_of_year: int, utc_hour: float
) -> Union[float, ndarray]:
    """根据地方太阳时计算时角（度）。"""
    solar_time = calc_solar_time(longitudes, day_of_year, utc_hour)
    return (solar_time - 12.0) * 15.0


def calc_solar_elevation(
    latitudes: Union[float, ndarray],
    longitudes: Union[float, ndarray],
    day_of_year: int,
    utc_hour: float,
    return_sine: bool = False,
) -> Union[float, ndarray]:
    """计算太阳高度角（度）。"""
    latitudes = np.asarray(latitudes)
    longitudes = np.asarray(longitudes)
    if np.min(latitudes) < -90.0 or np.max(latitudes) > 90.0:
        raise ValueError("Latitudes must be between -90.0 and 90.0")
    if np.min(longitudes) < -180.0 or np.max(longitudes) > 360.0:
        raise ValueError("Longitudes must be between -180.0 and 360.0")
    if day_of_year < 0 or day_of_year > DAYS_IN_YEAR:
        raise ValueError("Day of the year must be between 0 and 365")
    if utc_hour < 0.0 or utc_hour > 24.0:
        raise ValueError("Hour must be between 0 and 24.0")

    decl = np.radians(calc_solar_declination(day_of_year))
    rad_hours = np.radians(calc_solar_hour_angle(longitudes, day_of_year, utc_hour))
    lats = np.radians(latitudes)
    solar_elevation = np.sin(decl) * np.sin(lats) + np.cos(decl) * np.cos(lats) * np.cos(
        rad_hours
    )
    if not return_sine:
        solar_elevation = np.degrees(np.arcsin(solar_elevation))
    return solar_elevation

