#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""把地形增强场叠加或扣除到降水预报上的命令行。

降水预报须已经在地形增强场同一张网格上。本入口不做重采样。

在本包目录执行::

    python cli/dsc_apply_orographic_enhancement.py --precip-path PATH --orographic-enhancement-path PATH
    python -m cli.dsc_apply_orographic_enhancement --precip-path PATH --orographic-enhancement-path PATH

Python::

    from cli.dsc_apply_orographic_enhancement import DscApplyOrographicEnhancementCli
    DscApplyOrographicEnhancementCli.call(precip_path="PATH", orographic_enhancement_path="PATH")
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
    """沿用原脚本：把 00temp 放进 sys.path，并让包根上的 utils 优先。"""
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.conf_ini import overlay_none


def process(
    precip_path: str,
    orographic_enhancement_path: str,
    output_path: Optional[str] = None,
    *,
    operation: Optional[str] = None,
    allowed_time_diff: Optional[int] = None,
    config=None,
) -> xr.DataArray:
    """对降水预报叠加或扣除地形增强。

    参数
    ----------
    precip_path : str
        降水预报 nc 文件路径。网格须与地形增强场一致。
    orographic_enhancement_path : str
        地形增强场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    operation : str, optional
        ``add`` 为叠加，``subtract`` 为扣除。省略则用 ``add``，
        仍可由 ``resource/conf.ini`` 的 ``operation`` 覆盖。
    allowed_time_diff : int, optional
        多时次增强场与降水时次匹配的容差，单位秒。省略则用 ``1800``，
        仍可由 ini 的 ``allowed_time_diff`` 覆盖。
    config : str, optional
        运行配置 ini。省略则用包内 ``resource/conf.ini``。

    返回
    -------
    xr.DataArray
        订正后的降水场。
    """
    # 显式参数 > ini 非空项 > 代码预设。
    _over = overlay_none(
        __file__,
        config,
        {
            "output_path": (output_path, "str"),
            "operation": (operation, "str"),
            "allowed_time_diff": (allowed_time_diff, "int"),
        },
    )
    output_path = _over["output_path"]
    operation = _over["operation"] if _over["operation"] is not None else "add"
    allowed_time_diff = (
        _over["allowed_time_diff"] if _over["allowed_time_diff"] is not None else 1800
    )
    from orographic_precipitation_downscaling.src.apply_orographic_enhancement import (
        ApplyOrographicEnhancement,
    )

    _unbounded = (-np.inf, np.inf, np.nan)
    precip = meb.checkout_griddata(
        meb.read_griddata_from_nc(precip_path), valid_val=_unbounded
    )
    orographic_enhancement = meb.checkout_griddata(
        meb.read_griddata_from_nc(orographic_enhancement_path), valid_val=_unbounded
    )

    result = ApplyOrographicEnhancement(operation)(
        precip,
        orographic_enhancement,
        allowed_time_diff=allowed_time_diff,
    )

    if output_path is not None:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "precipitation"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")

    return result


class DscApplyOrographicEnhancementCli(CliBase):
    """``dsc_apply_orographic_enhancement`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_apply_orographic_enhancement.py"
    description = (
        "把地形增强场叠加或扣除到降水预报。\n"
        "降水与增强场路径必填，且须已在同一网格。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_apply_orographic_enhancement.py --help\n"
        "  python cli/dsc_apply_orographic_enhancement.py --precip-path PATH "
        "--orographic-enhancement-path PATH --output-path OUT.nc --operation add\n"
        "  python -m cli.dsc_apply_orographic_enhancement --precip-path PATH "
        "--orographic-enhancement-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip-path", required=True, metavar="PATH", help="降水预报 NetCDF。必填。")
        parser.add_argument(
            "--orographic-enhancement-path",
            required=True,
            metavar="PATH",
            help="地形增强场 NetCDF。必填。",
        )
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument(
            "--operation",
            default=None,
            choices=["add", "subtract"],
            help="add 叠加，subtract 扣除。省略则用 add。",
        )
        parser.add_argument(
            "--allowed-time-diff",
            dest="allowed_time_diff",
            type=int,
            default=None,
            help="增强场与降水时次匹配容差（秒）。省略则用 1800。",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_apply_orographic_enhancement_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_apply_orographic_enhancement`` 都进这里。"""
    return DscApplyOrographicEnhancementCli().main(argv)


main = dsc_apply_orographic_enhancement_cli


if __name__ == "__main__":
    raise SystemExit(dsc_apply_orographic_enhancement_cli())
