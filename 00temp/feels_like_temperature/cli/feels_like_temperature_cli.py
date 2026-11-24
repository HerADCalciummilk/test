# -*- coding: utf-8 -*-
"""体感温度调度。

``@merge_params`` 挂在 ``process`` 上。读四场 nc，调用 ``FeelsLikeTemperature``，按需写盘。
由 ``python -m feels_like_temperature`` 或 ``python -m cli`` 启动。
"""
from __future__ import annotations

import os
import sys

import numpy as np

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb

from feels_like_temperature.src.feels_like_temperature import FeelsLikeTemperature
from utils.merge_params import merge_params


@merge_params()
def process(
    temperature_path=None,
    wind_speed_path=None,
    relative_humidity_path=None,
    pressure_path=None,
    output_path=None,
    config=None,
):
    """读气温、风速、相对湿度和气压，计算体感温度。``config`` 只换配置文件。"""
    _ = config
    missing = [
        name
        for name, value in (
            ("temperature_path", temperature_path),
            ("wind_speed_path", wind_speed_path),
            ("relative_humidity_path", relative_humidity_path),
            ("pressure_path", pressure_path),
        )
        if value is None or not str(value).strip()
    ]
    if missing:
        raise ValueError("缺少参数: %s" % ", ".join(missing))

    _valid_val = (-np.inf, np.inf, np.nan)
    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_valid_val
    )
    wind_speed = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_speed_path), valid_val=_valid_val
    )
    relative_humidity = meb.checkout_griddata(
        meb.read_griddata_from_nc(relative_humidity_path), valid_val=_valid_val
    )
    pressure = meb.checkout_griddata(
        meb.read_griddata_from_nc(pressure_path), valid_val=_valid_val
    )

    for label, field in (
        ("风速场", wind_speed),
        ("相对湿度场", relative_humidity),
        ("气压场", pressure),
    ):
        if not meb.checkout_griddata_same_coords(
            [temperature, field], is_time_match=True
        ):
            raise ValueError("%s与温度场的空间/时效坐标不一致" % label)

    result = FeelsLikeTemperature().process(
        temperature=temperature,
        wind_speed=wind_speed,
        relative_humidity=relative_humidity,
        pressure=pressure,
    )
    if output_path:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)
    return result
