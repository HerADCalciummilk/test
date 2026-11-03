#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""地形带权重辅助场生成 CLI。

在本包目录执行::

    python -m cli.dsc_generate_topographic_zone_weights --orography-path orog.nc --output-path out.nc
    python cli/dsc_generate_topographic_zone_weights.py --orography-path orog.nc --output-path out.nc

Python::

    from cli.dsc_generate_topographic_zone_weights import DscGenerateTopographicZoneWeightsCli
    DscGenerateTopographicZoneWeightsCli.call(orography_path="orog.nc", output_path="out.nc")
"""
from __future__ import annotations

import argparse
import json
import sys
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


def process(
    orography_path: str,
    landmask_path: Optional[str] = None,
    thresholds_path: Optional[str] = None,
    output_path: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """读取输入数据并生成地形带折叠权重。

    读取地形高度与可选海陆掩码，生成各地形带权重：格点在带中心时该带权重为 1.0；
    在带边界时上下带各为 0.5；其余在中心与边界之间线性变化。

    参数
    ----------
    orography_path : str
        标准网格地形高度场 nc 路径。
    landmask_path : str, optional
        标准网格海陆掩码 nc 路径（陆=1，海=0）。若提供则屏蔽海点；
        为空时对陆点与海点均生成权重。
    thresholds_path : str, optional
        地形带配置 JSON 路径。字典格式示例::

            {"bounds": [[0, 50], [50, 200]], "units": "m"}

        为空时使用默认 ``THRESHOLDS_DICT``，形如::

            {
                "bounds": [
                    [-500.0, 50.0], [50.0, 100.0], [100.0, 150.0],
                    [150.0, 200.0], [200.0, 250.0], [250.0, 300.0],
                    [300.0, 400.0], [400.0, 500.0], [500.0, 650.0],
                    [650.0, 800.0], [800.0, 950.0], [950.0, 6000.0],
                ],
                "units": "m",
            }

    output_path : str, optional
        输出 nc 路径；为空时仅返回结果。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        沿 ``level`` 维堆叠的地形带权重（meteva_base 六维）。
    """
    from generate_ancillary.src.generate_ancillary import THRESHOLDS_DICT
    from generate_ancillary.src.generate_topographic_zone_weights import (
        GenerateTopographicZoneWeights,
    )

    orography = meb.read_griddata_from_nc(orography_path)

    if thresholds_path is None:
        thresholds_dict = THRESHOLDS_DICT
    else:
        with open(thresholds_path, "r", encoding="utf-8") as input_file:
            thresholds_dict = json.load(input_file)

    landmask = (
        meb.read_griddata_from_nc(landmask_path) if landmask_path is not None else None
    )

    result = GenerateTopographicZoneWeights().process(
        orography=orography,
        thresholds_dict=thresholds_dict,
        landmask=landmask,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


class DscGenerateTopographicZoneWeightsCli(CliBase):
    """按海拔阈值生成地形带折叠权重。"""

    prog = "python -m cli.dsc_generate_topographic_zone_weights"
    description = (
        "按海拔阈值生成地形带权重：带中心为 1，带边界上下带各 0.5。\n"
        "提供海陆掩码时屏蔽海点。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.dsc_generate_topographic_zone_weights --help\n"
        "  python -m cli.dsc_generate_topographic_zone_weights "
        "--orography-path orog.nc --landmask-path land.nc --output-path out.nc\n"
        "  python cli/dsc_generate_topographic_zone_weights.py "
        "--orography-path orog.nc --thresholds-path bounds.json --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - 省略 --thresholds-path 时使用包内默认地形带\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--orography-path",
            dest="orography_path",
            required=True,
            metavar="PATH",
            help="标准网格地形高度场 nc。",
        )
        parser.add_argument(
            "--landmask-path",
            dest="landmask_path",
            default=None,
            metavar="PATH",
            help="海陆掩码 nc（陆=1，海=0）。省略则陆海都生成权重。",
        )
        parser.add_argument(
            "--thresholds-path",
            dest="thresholds_path",
            default=None,
            metavar="PATH",
            help='地形带 JSON，如 {"bounds": [[0, 50]], "units": "m"}。省略则用默认带。',
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
        orography_path=None,
        landmask_path=None,
        thresholds_path=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            orography_path=orography_path,
            landmask_path=landmask_path,
            thresholds_path=thresholds_path,
            output_path=output_path,
            config=config,
        )
        return 0


def dsc_generate_topographic_zone_weights_cli(
    argv: Optional[Sequence[str]] = None,
) -> int:
    """命令行入口。``python -m cli.dsc_generate_topographic_zone_weights`` 与直接运行本文件都进这里。"""
    return DscGenerateTopographicZoneWeightsCli().main(argv)


main = dsc_generate_topographic_zone_weights_cli


if __name__ == "__main__":
    raise SystemExit(dsc_generate_topographic_zone_weights_cli())
