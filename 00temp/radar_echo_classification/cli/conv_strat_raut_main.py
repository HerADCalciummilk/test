#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Raut 小波对流/层状分类命令行。

在本包目录执行::

    python cli/conv_strat_raut_main.py --refl-path PATH [--output-path PATH]
    python -m cli.conv_strat_raut_main --refl-path PATH

Python::

    from cli.conv_strat_raut_main import ConvStratRautMainCli
    ConvStratRautMainCli.call(refl_path="PATH")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
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
    refl_path: str,
    *,
    cappi_level: float = 0,
    zr_a: float = 200,
    zr_b: float = 1.6,
    core_wt_threshold: float = 5,
    conv_wt_threshold: float = 1.5,
    conv_scale_km: float = 25,
    min_reflectivity: float = 5,
    conv_min_refl: float = 25,
    conv_core_threshold: float = 42,
    override_checks: bool = False,
    output_path: Optional[str] = None, config=None) -> xr.DataArray:
    """使用 Raut 多分辨率小波方法区分层状、混合和对流核心回波。

    参数
    ----
    refl_path : str
        输入反射率网格 NetCDF 文件路径。
    cappi_level : float or int, optional
        分类层，可传层索引或高度值。
    zr_a, zr_b : float, optional
        反射率转换雨强时使用的 Z-R 关系系数。
    core_wt_threshold : float, optional
        对流核心与混合回波之间的小波阈值。
    conv_wt_threshold : float, optional
        对流与层状回波之间的小波阈值。
    conv_scale_km : float, optional
        对流、层状尺度分割长度，单位千米。
    min_reflectivity : float, optional
        参与分类的最小反射率阈值，单位 dBZ。
    conv_min_refl : float, optional
        判为对流或混合所需的最小反射率，单位 dBZ。
    conv_core_threshold : float, optional
        初始对流核心反射率阈值，单位 dBZ。当前原版同源分类逻辑中，
        该判据随后会被核心小波判据重写，通常不单独影响最终结果。
    override_checks : bool, optional
        是否跳过推荐参数范围的夹紧检查。
    output_path : str, optional
        结果 NetCDF 输出路径；为空时仅返回内存结果。

    返回
    ----
    xr.DataArray
        单层小波分类网格：0=未分类，1=层状，2=混合，3=对流核心。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "output_path": (output_path, "str"),
    })
    output_path = _over['output_path']
    from radar_echo_classification.src.echo_class import ConvStratRautPlugin

    refl = meb.read_griddata_from_nc(refl_path)
    plugin = ConvStratRautPlugin(
        cappi_level=cappi_level,
        zr_a=zr_a,
        zr_b=zr_b,
        core_wt_threshold=core_wt_threshold,
        conv_wt_threshold=conv_wt_threshold,
        conv_scale_km=conv_scale_km,
        min_reflectivity=min_reflectivity,
        conv_min_refl=conv_min_refl,
        conv_core_threshold=conv_core_threshold,
        override_checks=override_checks,
    )
    result = plugin(refl)
    if output_path is not None:
        from radar_echo_classification.cli import save_echo_class_grid_to_netcdf

        save_echo_class_grid_to_netcdf(result, output_path)
    return result


class ConvStratRautMainCli(CliBase):
    """``conv_strat_raut_main`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/conv_strat_raut_main.py"
    description = (
        "Raut 小波对流/层状分类。\n"
        "必填路径由命令行传入。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/conv_strat_raut_main.py --help\n"
        "  python cli/conv_strat_raut_main.py --refl-path PATH --output-path OUT.nc\n"
        "  python -m cli.conv_strat_raut_main --refl-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--refl-path", required=True, metavar="PATH", help="输入反射率网格 NetCDF。必填。")
        parser.add_argument("--cappi-level", dest="cappi_level", type=float, default=None, help="分类层索引或高度。省略则用 0。")
        parser.add_argument("--zr-a", dest="zr_a", type=float, default=None, help="Z-R 系数 a。省略则用 200。")
        parser.add_argument("--zr-b", dest="zr_b", type=float, default=None, help="Z-R 系数 b。省略则用 1.6。")
        parser.add_argument("--core-wt-threshold", dest="core_wt_threshold", type=float, default=None, help="对流核心小波阈值。省略则用 5。")
        parser.add_argument("--conv-wt-threshold", dest="conv_wt_threshold", type=float, default=None, help="对流/层状小波阈值。省略则用 1.5。")
        parser.add_argument("--conv-scale-km", dest="conv_scale_km", type=float, default=None, help="对流尺度分割（千米）。省略则用 25。")
        parser.add_argument("--min-reflectivity", dest="min_reflectivity", type=float, default=None, help="最小反射率（dBZ）。省略则用 5。")
        parser.add_argument("--conv-min-refl", dest="conv_min_refl", type=float, default=None, help="对流或混合的最小反射率（dBZ）。省略则用 25。")
        parser.add_argument("--conv-core-threshold", dest="conv_core_threshold", type=float, default=None, help="初始对流核心反射率阈值（dBZ）。省略则用 42。")
        self.add_optional_bool(parser, "--override-checks", help_true="跳过推荐参数范围夹紧。", help_false="保留参数范围夹紧。省略则用函数默认值 false。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="结果 NetCDF。省略则只返回内存结果。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def conv_strat_raut_main_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.conv_strat_raut_main`` 都进这里。"""
    return ConvStratRautMainCli().main(argv)


main = conv_strat_raut_main_cli


if __name__ == "__main__":
    raise SystemExit(conv_strat_raut_main_cli())
