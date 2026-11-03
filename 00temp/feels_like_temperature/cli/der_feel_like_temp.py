#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""计算体感温度的 CLI。

在本包目录执行::

    python -m cli.der_feel_like_temp --temperature-path t.nc --wind-speed-path w.nc --relative-humidity-path rh.nc --pressure-path p.nc --output-path out.nc
    python cli/der_feel_like_temp.py --temperature-path t.nc --wind-speed-path w.nc --relative-humidity-path rh.nc --pressure-path p.nc --output-path out.nc

Python::

    from cli.der_feel_like_temp import DerFeelLikeTempCli
    DerFeelLikeTempCli.call(
        temperature_path="t.nc",
        wind_speed_path="w.nc",
        relative_humidity_path="rh.nc",
        pressure_path="p.nc",
        output_path="out.nc",
    )
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr
import meteva_base as meb


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def process(
    temperature_path: str,
    wind_speed_path: str,
    relative_humidity_path: str,
    pressure_path: str,
    output_path: Optional[str] = None,
    config=None,
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
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

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


class DerFeelLikeTempCli(CliBase):
    """由气温、风速、相对湿度和气压计算体感温度。"""

    prog = "python -m cli.der_feel_like_temp"
    description = (
        "由屏幕高度气温、10 米风速、相对湿度和气压计算体感温度。\n"
        "四场须为同一时空网格的 meb 六维 nc。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.der_feel_like_temp --help\n"
        "  python -m cli.der_feel_like_temp "
        "--temperature-path t.nc --wind-speed-path w.nc "
        "--relative-humidity-path rh.nc --pressure-path p.nc --output-path out.nc\n"
        "  python cli/der_feel_like_temp.py "
        "--temperature-path t.nc --wind-speed-path w.nc "
        "--relative-humidity-path rh.nc --pressure-path p.nc --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--temperature-path",
            dest="temperature_path",
            required=True,
            metavar="PATH",
            help="屏幕高度气温场 nc。",
        )
        parser.add_argument(
            "--wind-speed-path",
            dest="wind_speed_path",
            required=True,
            metavar="PATH",
            help="10 米风速场 nc。",
        )
        parser.add_argument(
            "--relative-humidity-path",
            dest="relative_humidity_path",
            required=True,
            metavar="PATH",
            help="屏幕高度相对湿度场 nc。",
        )
        parser.add_argument(
            "--pressure-path",
            dest="pressure_path",
            required=True,
            metavar="PATH",
            help="气压场 nc（海平面气压或地面气压）。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="输出 nc。省略则只返回、不写文件。",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置文件，传给 process 的 config。"
                "相对路径按项目根解析。"
                "本模块无 ini 读取器，省略则不改路径。"
            ),
        )

    def run(
        self,
        temperature_path=None,
        wind_speed_path=None,
        relative_humidity_path=None,
        pressure_path=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            temperature_path=temperature_path,
            wind_speed_path=wind_speed_path,
            relative_humidity_path=relative_humidity_path,
            pressure_path=pressure_path,
            output_path=output_path,
            config=config,
        )
        return 0


def der_feel_like_temp_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.der_feel_like_temp`` 与直接运行本文件都进这里。"""
    return DerFeelLikeTempCli().main(argv)


main = der_feel_like_temp_cli


if __name__ == "__main__":
    raise SystemExit(der_feel_like_temp_cli())
