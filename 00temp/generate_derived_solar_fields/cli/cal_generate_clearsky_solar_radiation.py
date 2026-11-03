#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""晴空太阳辐射累计计算 CLI。

在本包目录执行::

    python -m cli.cal_generate_clearsky_solar_radiation --target-grid-path grid.nc --time 2022050600 --accumulation-period 24 --output-path out.nc
    python cli/cal_generate_clearsky_solar_radiation.py --target-grid-path grid.nc --time 2022050600 --accumulation-period 24 --output-path out.nc

Python::

    from cli.cal_generate_clearsky_solar_radiation import CalGenerateClearskySolarRadiationCli
    CalGenerateClearskySolarRadiationCli.call(
        target_grid_path="grid.nc",
        time="2022050600",
        accumulation_period=24,
        output_path="out.nc",
    )
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def _parse_datetime(text: str) -> datetime:
    value = str(text).strip()
    formats = (
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d%H",
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        "时间格式应为 YYYYMMDDHH、YYYYMMDDHHMM 或 YYYY-MM-DDTHH:MM:SS"
    )


def _set_kwargs(**kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


def process(
    target_grid_path: str,
    time: datetime,
    accumulation_period: int,
    surface_altitude_path: Optional[str] = None,
    linke_turbidity_path: Optional[str] = None,
    temporal_spacing: int = 30,
    new_title: Optional[str] = None,
    output_path: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """读取输入并计算指定时段内的累计晴空太阳辐射。

    参数
    ----------
    target_grid_path :
        目标网格 meb 六维 nc；通常与 ``surface_altitude_path`` 同网。
    time :
        累积结束时刻（``datetime``）。
    accumulation_period :
        累积时长（小时），如 ``24`` 表示过去 24 小时积分。
    surface_altitude_path :
        可选，地表海拔 meb nc（米）；不传则插件内使用默认海拔场。
    linke_turbidity_path :
        可选，Linke 浑浊度 meb nc；不传则插件内使用默认浑浊度场。
    temporal_spacing :
        时间积分步长（分钟），默认 ``30``。
    new_title :
        可选，写出前覆盖 ``attrs["title"]``。
    output_path :
        可选输出 nc 路径；为 ``None`` 时不写文件。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        累计晴空短波辐射（单位 ``W s m-2``），并附带时间窗与积分参数属性。
    """
    from generate_derived_solar_fields.src.generate_derived_solar_fields import (
        GenerateClearskySolarRadiation,
    )

    if not isinstance(time, datetime):
        raise TypeError("time 必须是 datetime。")

    target_grid = meb.read_griddata_from_nc(target_grid_path)
    surface_altitude = (
        meb.read_griddata_from_nc(surface_altitude_path)
        if surface_altitude_path is not None
        else None
    )
    linke_turbidity = (
        meb.read_griddata_from_nc(linke_turbidity_path)
        if linke_turbidity_path is not None
        else None
    )

    result = GenerateClearskySolarRadiation().process(
        target_grid=target_grid,
        time=time,
        accumulation_period=accumulation_period,
        surface_altitude=surface_altitude,
        linke_turbidity=linke_turbidity,
        temporal_spacing=temporal_spacing,
        new_title=new_title,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


class CalGenerateClearskySolarRadiationCli(CliBase):
    """计算指定时段内的累计晴空太阳辐射。"""

    prog = "python -m cli.cal_generate_clearsky_solar_radiation"
    description = (
        "在目标网格上积分累计晴空太阳辐射。\n"
        "地表海拔与 Linke 浑浊度可省略，省略时插件使用默认场。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.cal_generate_clearsky_solar_radiation --help\n"
        "  python -m cli.cal_generate_clearsky_solar_radiation "
        "--target-grid-path grid.nc --time 2022050600 "
        "--accumulation-period 24 --output-path out.nc\n"
        "  python cli/cal_generate_clearsky_solar_radiation.py "
        "--target-grid-path grid.nc --time 2022-05-06T00:00:00 "
        "--accumulation-period 24 --surface-altitude-path alt.nc "
        "--output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - 省略 --temporal-spacing 时 process 默认 30 分钟\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--target-grid-path",
            dest="target_grid_path",
            required=True,
            metavar="PATH",
            help="目标网格 meb 六维 nc。",
        )
        parser.add_argument(
            "--time",
            dest="time",
            type=_parse_datetime,
            required=True,
            metavar="TIME",
            help="累积结束时刻，如 2022050600 或 2022-05-06T00:00:00。",
        )
        parser.add_argument(
            "--accumulation-period",
            dest="accumulation_period",
            type=int,
            required=True,
            metavar="HOURS",
            help="累积时长（小时），如 24 表示过去 24 小时积分。",
        )
        parser.add_argument(
            "--surface-altitude-path",
            dest="surface_altitude_path",
            default=None,
            metavar="PATH",
            help="地表海拔 meb nc（米）。省略则插件使用默认海拔场。",
        )
        parser.add_argument(
            "--linke-turbidity-path",
            dest="linke_turbidity_path",
            default=None,
            metavar="PATH",
            help="Linke 浑浊度 meb nc。省略则插件使用默认浑浊度场。",
        )
        parser.add_argument(
            "--temporal-spacing",
            dest="temporal_spacing",
            type=int,
            default=None,
            metavar="MINUTES",
            help="时间积分步长（分钟）。省略则使用 30。",
        )
        parser.add_argument(
            "--new-title",
            dest="new_title",
            default=None,
            metavar="TEXT",
            help='写出前覆盖 attrs["title"]。',
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
        target_grid_path=None,
        time=None,
        accumulation_period=None,
        surface_altitude_path=None,
        linke_turbidity_path=None,
        temporal_spacing=None,
        new_title=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            target_grid_path=target_grid_path,
            time=time,
            accumulation_period=accumulation_period,
            surface_altitude_path=surface_altitude_path,
            linke_turbidity_path=linke_turbidity_path,
            new_title=new_title,
            output_path=output_path,
            config=config,
            **_set_kwargs(temporal_spacing=temporal_spacing),
        )
        return 0


def cal_generate_clearsky_solar_radiation_cli(
    argv: Optional[Sequence[str]] = None,
) -> int:
    """命令行入口。``python -m cli.cal_generate_clearsky_solar_radiation`` 与直接运行本文件都进这里。"""
    return CalGenerateClearskySolarRadiationCli().main(argv)


main = cal_generate_clearsky_solar_radiation_cli


if __name__ == "__main__":
    raise SystemExit(cal_generate_clearsky_solar_radiation_cli())
