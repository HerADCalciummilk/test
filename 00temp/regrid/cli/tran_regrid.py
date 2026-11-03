#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""海陆感知重网格 CLI。

在本包目录执行::

    python -m cli.tran_regrid --input-path in.nc --target-grid-path grid.nc --output-path out.nc
    python cli/tran_regrid.py --input-path in.nc --target-grid-path grid.nc --output-path out.nc

Python::

    from cli.tran_regrid import TranRegridCli
    TranRegridCli.call(
        input_path="in.nc",
        target_grid_path="grid.nc",
        output_path="out.nc",
    )
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def _set_kwargs(**kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


def process(
    input_path: str,
    target_grid_path: str,
    land_sea_mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    regrid_mode: str = "bilinear",
    extrapolation_mode: str = "nanmask",
    land_sea_mask_vicinity: float = 25000.0,
    regridded_title: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """将源场重网格到目标网格，可选海陆感知。

    考虑海陆掩码时，地表类型不匹配的源点不参与目标点插值。例如在最近邻
    海陆感知模式下，重网格后的陆点总是取自源网格陆点，海点总是取自源网格
    海点。

    参数
    ----------
    input_path :
        源场 nc 路径。
    target_grid_path :
        目标网格 nc 路径；掩码模式下应为目标海陆掩码场。
    land_sea_mask_path :
        源网格海陆掩码 nc；``*-with-mask*`` 模式必需。
    output_path :
        输出 nc 路径；为 None 时不写文件。
    regrid_mode :
        插值模式，如 ``bilinear`` / ``nearest`` / ``nearest-with-mask`` /
        ``bilinear-2`` / ``nearest-2`` / ``*-with-mask-2``。
    extrapolation_mode :
        源域外填充方式：``extrapolate``、``error``，以及
        ``nan`` / ``mask`` / ``nanmask``（三者等效，均填 NaN；默认 ``nanmask``）。
    land_sea_mask_vicinity :
        海岸线搜索半径，单位米。
    regridded_title :
        输出 ``title`` 属性；未指定时由插件使用默认值。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        重网格后的六维场。
    """
    from regrid.src.landsea import RegridLandSea

    _unbounded = (-np.inf, np.inf, np.nan)

    input_field = meb.checkout_griddata(
        meb.read_griddata_from_nc(input_path), valid_val=_unbounded
    )
    target_grid = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_grid_path), valid_val=_unbounded
    )

    land_sea_mask = None
    if land_sea_mask_path is not None:
        # 与上游 improver/cli/regrid.py 一致：提供掩码文件时须匹配掩码模式
        if regrid_mode not in (
            "nearest-with-mask",
            "nearest-with-mask-2",
            "bilinear-with-mask-2",
        ):
            raise ValueError(
                "Land-mask file supplied without appropriate regrid-mode. "
                "Use --regrid-mode nearest-with-mask."
            )
        land_sea_mask = meb.checkout_griddata(
            meb.read_griddata_from_nc(land_sea_mask_path), valid_val=_unbounded
        )

    result = RegridLandSea(
        regrid_mode=regrid_mode,
        extrapolation_mode=extrapolation_mode,
        landmask=land_sea_mask,
        landmask_vicinity=land_sea_mask_vicinity,
    )(input_field, target_grid, regridded_title=regridded_title)

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)

    return result


class TranRegridCli(CliBase):
    """将源场重网格到目标网格，可选海陆感知。"""

    prog = "python -m cli.tran_regrid"
    description = (
        "将源场重网格到目标网格。\n"
        "提供海陆掩码时须使用 nearest-with-mask、nearest-with-mask-2 "
        "或 bilinear-with-mask-2。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.tran_regrid --help\n"
        "  python -m cli.tran_regrid --input-path in.nc "
        "--target-grid-path grid.nc --output-path out.nc\n"
        "  python cli/tran_regrid.py --input-path in.nc "
        "--target-grid-path grid.nc --land-sea-mask-path mask.nc "
        "--regrid-mode nearest-with-mask --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - 省略 --regrid-mode 时 process 默认 bilinear\n"
        "  - 省略 --extrapolation-mode 时 process 默认 nanmask\n"
        "  - 省略 --land-sea-mask-vicinity 时 process 默认 25000（米）\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--input-path",
            dest="input_path",
            required=True,
            metavar="PATH",
            help="源场 nc。",
        )
        parser.add_argument(
            "--target-grid-path",
            dest="target_grid_path",
            required=True,
            metavar="PATH",
            help="目标网格 nc。掩码模式下应为目标海陆掩码场。",
        )
        parser.add_argument(
            "--land-sea-mask-path",
            dest="land_sea_mask_path",
            default=None,
            metavar="PATH",
            help="源网格海陆掩码 nc。*-with-mask* 模式必需。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="输出 nc。省略则只返回、不写文件。",
        )
        parser.add_argument(
            "--regrid-mode",
            dest="regrid_mode",
            default=None,
            metavar="MODE",
            help=(
                "插值模式，如 bilinear、nearest、nearest-with-mask、"
                "bilinear-2、nearest-2、*-with-mask-2。"
                "省略则使用 bilinear。"
            ),
        )
        parser.add_argument(
            "--extrapolation-mode",
            dest="extrapolation_mode",
            default=None,
            metavar="MODE",
            help=(
                "源域外填充：extrapolate、error，或 nan/mask/nanmask。"
                "省略则使用 nanmask。"
            ),
        )
        parser.add_argument(
            "--land-sea-mask-vicinity",
            dest="land_sea_mask_vicinity",
            type=float,
            default=None,
            metavar="METRES",
            help="海岸线搜索半径，单位米。省略则使用 25000。",
        )
        parser.add_argument(
            "--regridded-title",
            dest="regridded_title",
            default=None,
            metavar="TEXT",
            help="输出 title 属性。省略则由插件使用默认值。",
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
        input_path=None,
        target_grid_path=None,
        land_sea_mask_path=None,
        output_path=None,
        regrid_mode=None,
        extrapolation_mode=None,
        land_sea_mask_vicinity=None,
        regridded_title=None,
        config=None,
    ) -> int:
        process(
            input_path,
            target_grid_path,
            land_sea_mask_path=land_sea_mask_path,
            output_path=output_path,
            regridded_title=regridded_title,
            config=config,
            **_set_kwargs(
                regrid_mode=regrid_mode,
                extrapolation_mode=extrapolation_mode,
                land_sea_mask_vicinity=land_sea_mask_vicinity,
            ),
        )
        return 0


def tran_regrid_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.tran_regrid`` 与直接运行本文件都进这里。"""
    return TranRegridCli().main(argv)


main = tran_regrid_cli


if __name__ == "__main__":
    raise SystemExit(tran_regrid_cli())
