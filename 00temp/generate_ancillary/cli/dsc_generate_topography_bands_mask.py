#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""地形带掩码辅助场生成 CLI。

在本包目录执行::

    python -m cli.dsc_generate_topography_bands_mask --orography-path orog.nc --output-path out.nc
    python cli/dsc_generate_topography_bands_mask.py --orography-path orog.nc --output-path out.nc

Python::

    from cli.dsc_generate_topography_bands_mask import DscGenerateTopographyBandsMaskCli
    DscGenerateTopographyBandsMaskCli.call(orography_path="orog.nc", output_path="out.nc")
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
    """读取输入数据并生成地形带掩码辅助场。

    按海拔阈值将地形高度场分带，每个带输出二值掩码（带内陆点为 1）。
    若提供海陆掩码，则每个带内海点置 0；若不提供，则陆海均参与分带。

    参数
    ----------
    orography_path : str
        标准网格地形高度场 nc 路径。
    landmask_path : str, optional
        标准网格海陆掩码 nc 路径（陆=1，海=0）。若提供则每个带内海点置 0；
        为空时对陆点与海点均生成掩码。
    thresholds_path : str, optional
        地形带配置 JSON 路径。字典格式示例::

            {"bounds": [[0, 100], [100, 200]], "units": "m"}

        为空时使用默认 ``THRESHOLDS_DICT``（约 ``[-500, 50], [50, 100], …,
        [950, 6000]``，单位 ``m``，见 ``generate_ancillary.THRESHOLDS_DICT``）。
    output_path : str, optional
        输出 nc 路径；为空时仅返回结果。写盘时结果转为 ``float32``。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        沿 ``level`` 维堆叠的地形带掩码（meteva_base 六维）。
    """
    from generate_ancillary.src.generate_ancillary import (
        THRESHOLDS_DICT,
        GenerateOrographyBandAncils,
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

    result = GenerateOrographyBandAncils().process(
        orography=orography,
        thresholds_dict=thresholds_dict,
        landmask=landmask,
    )

    if output_path is not None:
        # meteva_base 写盘默认使用 scale_factor + int32 编码；
        # 对 int32 掩码直接写盘会触发 xarray 编码阶段的 dtype 冲突。
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


class DscGenerateTopographyBandsMaskCli(CliBase):
    """按海拔阈值生成地形带掩码辅助场。"""

    prog = "python -m cli.dsc_generate_topography_bands_mask"
    description = (
        "按海拔阈值把地形高度场分成若干带，每带输出二值掩码。\n"
        "提供海陆掩码时，带内海点置 0。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.dsc_generate_topography_bands_mask --help\n"
        "  python -m cli.dsc_generate_topography_bands_mask "
        "--orography-path orog.nc --landmask-path land.nc --output-path out.nc\n"
        "  python cli/dsc_generate_topography_bands_mask.py "
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
            help="海陆掩码 nc（陆=1，海=0）。省略则陆海都参与分带。",
        )
        parser.add_argument(
            "--thresholds-path",
            dest="thresholds_path",
            default=None,
            metavar="PATH",
            help='地形带 JSON，如 {"bounds": [[0, 100]], "units": "m"}。省略则用默认带。',
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


def dsc_generate_topography_bands_mask_cli(
    argv: Optional[Sequence[str]] = None,
) -> int:
    """命令行入口。``python -m cli.dsc_generate_topography_bands_mask`` 与直接运行本文件都进这里。"""
    return DscGenerateTopographyBandsMaskCli().main(argv)


main = dsc_generate_topography_bands_mask_cli


if __name__ == "__main__":
    raise SystemExit(dsc_generate_topography_bands_mask_cli())
