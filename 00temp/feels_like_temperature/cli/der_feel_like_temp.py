#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""计算体感温度的 CLI 示例。

约定（无 Improver ``cli`` 装饰器）::

    - ``process`` 接收文件路径，在函数内完成读入、计算与可选写出；
    - ``main`` 中定义路径等参数，再直接调用 ``process``。

包根目录执行::

    python -m cli feel-like-temp
    python cli/der_feel_like_temp.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import numpy as np
import xarray as xr
import meteva_base as meb

# 本包根目录（含 resource/、src/、cli/）
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def process(
    temperature_path: str,
    wind_speed_path: str,
    relative_humidity_path: str,
    pressure_path: str,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """根据气温、风速、相对湿度和气压计算体感温度。

    输入须为 meb 六维网格 nc（member, level, time, dtime, lat, lon），
    空间维为经纬坐标；四场时空坐标须一致。在函数内完成读盘与可选写盘。

    参数
    ----------
    temperature_path : str
        屏幕高度气温场 nc 文件路径。
    wind_speed_path : str
        10 米风速场 nc 文件路径。
    relative_humidity_path : str
        屏幕高度相对湿度场 nc 文件路径。
    pressure_path : str
        气压场 nc 文件路径（海平面气压或地面气压，按单位自动换算）。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。

    返回
    -------
    xr.DataArray
        体感温度场（与输入同为 meb 六维）。
    """
    from feels_like_temperature.src.feels_like_temperature import (
        calculate_feels_like_temperature,
    )

    # 读盘后做 meb 网格校验（不截断数值范围）
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

    # 以气温场为基准，校验其余场空间/时效坐标一致
    for label, field in (
        ("风速场", wind_speed),
        ("相对湿度场", relative_humidity),
        ("气压场", pressure),
    ):
        if not meb.checkout_griddata_same_coords(
            [temperature, field], is_time_match=True
        ):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    result = calculate_feels_like_temperature(
        temperature=temperature,
        wind_speed=wind_speed,
        relative_humidity=relative_humidity,
        pressure=pressure,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)

    return result


def main() -> None:
    """定义输入/输出路径并调用 ``process``。

    默认使用 ``resource/cli_input`` 下经纬 meb 六维样例；业务使用时在此修改路径即可。
    """
    # 保证可 ``from feels_like_temperature...``（直接运行本脚本时）
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    input_dir = _PACKAGE_ROOT / "resource" / "cli_input"
    output_dir = _PACKAGE_ROOT / "resource" / "cli_output"

    temperature_path = str(
        input_dir / "20181121T1200Z-PT0012H00M-temperature_at_screen_level.nc"
    )
    wind_speed_path = str(
        input_dir / "20181121T1200Z-PT0012H00M-wind_speed_at_10m.nc"
    )
    relative_humidity_path = str(
        input_dir / "20181121T1200Z-PT0012H00M-relative_humidity_at_screen_level.nc"
    )
    pressure_path = str(
        input_dir / "20181121T1200Z-PT0012H00M-pressure_at_mean_sea_level.nc"
    )
    output_path = str(output_dir / "cli_feels_like_temp_result.nc")

    process(
        temperature_path=temperature_path,
        wind_speed_path=wind_speed_path,
        relative_humidity_path=relative_humidity_path,
        pressure_path=pressure_path,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
