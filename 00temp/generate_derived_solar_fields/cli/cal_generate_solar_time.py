#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地方太阳时计算 CLI。

在本包目录执行::

    python -m cli.cal_generate_solar_time --target-grid-path grid.nc --time 2022060700 --output-path out.nc
    python cli/cal_generate_solar_time.py --target-grid-path grid.nc --time 2022060700 --output-path out.nc

Python::

    from cli.cal_generate_solar_time import CalGenerateSolarTimeCli
    CalGenerateSolarTimeCli.call(
        target_grid_path="grid.nc",
        time="2022060700",
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


def process(
    target_grid_path: str,
    time: datetime,
    new_title: Optional[str] = None,
    output_path: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """读取目标网格并计算地方太阳时。

    参数
    ----------
    target_grid_path :
        目标网格 meb 六维 nc（``member, level, time, dtime, lat, lon``）。
        投影输入须含 ``grid_mapping_attrs``；亦可使用预处理后的经纬 meb。
    time :
        计算时刻（``datetime``），用于推算地方太阳时。
    new_title :
        可选，写出前覆盖 ``attrs["title"]``。
    output_path :
        可选输出 nc 路径；为 ``None`` 时不写文件。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        地方太阳时场（``local_solar_time``，单位 hours，范围 0–24）。
    """
    from generate_derived_solar_fields.src.generate_derived_solar_fields import (
        GenerateSolarTime,
    )

    if not isinstance(time, datetime):
        raise TypeError("time 必须是 datetime。")

    target_grid = meb.read_griddata_from_nc(target_grid_path)
    result = GenerateSolarTime().process(
        target_grid=target_grid,
        time=time,
        new_title=new_title,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


class CalGenerateSolarTimeCli(CliBase):
    """在目标网格上计算地方太阳时。"""

    prog = "python -m cli.cal_generate_solar_time"
    description = "读取目标网格，按给定时刻计算地方太阳时（0–24 小时）。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.cal_generate_solar_time --help\n"
        "  python -m cli.cal_generate_solar_time "
        "--target-grid-path grid.nc --time 2022060700 --output-path out.nc\n"
        "  python cli/cal_generate_solar_time.py "
        "--target-grid-path grid.nc --time 2022-06-07T00:00:00 --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--target-grid-path",
            dest="target_grid_path",
            required=True,
            metavar="PATH",
            help="目标网格 meb 六维 nc。投影输入须含 grid_mapping_attrs。",
        )
        parser.add_argument(
            "--time",
            dest="time",
            type=_parse_datetime,
            required=True,
            metavar="TIME",
            help="计算时刻，如 2022060700 或 2022-06-07T00:00:00。",
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
        new_title=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            target_grid_path=target_grid_path,
            time=time,
            new_title=new_title,
            output_path=output_path,
            config=config,
        )
        return 0


def cal_generate_solar_time_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.cal_generate_solar_time`` 与直接运行本文件都进这里。"""
    return CalGenerateSolarTimeCli().main(argv)


main = cal_generate_solar_time_cli


if __name__ == "__main__":
    raise SystemExit(cal_generate_solar_time_cli())
