#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""特征识别命令行。

在本包目录执行::

    python cli/feature_detection_main.py --field-data-path PATH [--output-path PATH]
    python -m cli.feature_detection_main --field-data-path PATH

Python::

    from cli.feature_detection_main import FeatureDetectionMainCli
    FeatureDetectionMainCli.call(field_data_path="PATH")
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
    field_data_path: str,
    *,
    overest_field_path: str = None,
    underest_field_path: str = None,
    dx: float = None,
    dy: float = None,
    level_m: float = None,
    always_core_thres: float = 42,
    bkg_rad_km: float = 11,
    use_cosine: bool = True,
    max_diff: float = 5,
    zero_diff_cos_val: float = 55,
    scalar_diff: float = 1.5,
    use_addition: bool = True,
    calc_thres: float = 0.75,
    weak_echo_thres: float = 5.0,
    min_val_used: float = 5.0,
    dB_averaging: bool = True,
    remove_small_objects: bool = True,
    min_km2_size: float = 10,
    binary_close: bool = False,
    val_for_max_rad: float = 30,
    max_rad_km: float = 5.0,
    core_val: int = 3,
    nosfcecho: int = 0,
    weakecho: int = 3,
    bkgd_val: int = 1,
    feat_val: int = 2,
    estimate_flag: bool = True,
    estimate_offset: float = 5,
    result_key: str = None,
    output_path: Optional[str] = None, config=None) -> xr.DataArray | xr.Dataset:
    """使用自适应阈值方法识别雷达回波中的核心与特征区域。

    参数
    ----
    field_data_path : str
        主输入网格 NetCDF 文件路径，通常为反射率场。
    overest_field_path, underest_field_path : str, optional
        显式高估、低估输入场文件路径；为空时算法以主场加减
        ``estimate_offset`` 构造敏感性试验输入。
    dx, dy : float, optional
        水平分辨率，单位米；为空时自动估算。
    level_m : float, optional
        参与分类的高度，单位米；为空时使用第一层。
    always_core_thres : float, optional
        始终判为核心回波的阈值。
    bkg_rad_km : float, optional
        背景场计算半径，单位千米。
    use_cosine, max_diff, zero_diff_cos_val, scalar_diff, use_addition, calc_thres
        自适应阈值关系及其控制参数。
    weak_echo_thres, min_val_used, dB_averaging
        弱回波、最小参与计算场值及背景平均策略。
    remove_small_objects, min_km2_size, binary_close
        小目标移除与二值形态学处理参数。
    val_for_max_rad, max_rad_km : float, optional
        特征影响半径的控制参数，单位千米。
    core_val, nosfcecho, weakecho, bkgd_val, feat_val : int, optional
        输出中核心、无回波、弱回波、背景和特征的类别编码。
    estimate_flag : bool, optional
        是否计算高估、低估敏感性结果。
    estimate_offset : float, optional
        未提供显式高估/低估场时，构造它们使用的场值偏移量。
    result_key : str, optional
        指定时仅返回该结果字段，例如 ``feature_detection``；
        为空时返回含所有字段的 ``xr.Dataset``。
    output_path : str, optional
        结果 NetCDF 输出路径；为空时仅返回内存结果。

    返回
    ----
    xr.DataArray or xr.Dataset
        ``result_key`` 被指定时为对应分类场；否则为包含
        ``feature_detection``，以及可选 ``feature_under``、
        ``feature_over`` 的数据集。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "overest_field_path": (overest_field_path, "str"),
        "underest_field_path": (underest_field_path, "str"),
        "dx": (dx, "float"),
        "dy": (dy, "float"),
        "level_m": (level_m, "float"),
        "result_key": (result_key, "str"),
        "output_path": (output_path, "str"),
    })
    overest_field_path = _over['overest_field_path']
    underest_field_path = _over['underest_field_path']
    dx = _over['dx']
    dy = _over['dy']
    level_m = _over['level_m']
    result_key = _over['result_key']
    output_path = _over['output_path']
    from radar_echo_classification.src.echo_class import FeatureDetectionPlugin

    field_data = meb.read_griddata_from_nc(field_data_path)
    overest_field = meb.read_griddata_from_nc(overest_field_path) if overest_field_path is not None else None
    underest_field = meb.read_griddata_from_nc(underest_field_path) if underest_field_path is not None else None
    plugin = FeatureDetectionPlugin(
        dx=dx,
        dy=dy,
        level_m=level_m,
        always_core_thres=always_core_thres,
        bkg_rad_km=bkg_rad_km,
        use_cosine=use_cosine,
        max_diff=max_diff,
        zero_diff_cos_val=zero_diff_cos_val,
        scalar_diff=scalar_diff,
        use_addition=use_addition,
        calc_thres=calc_thres,
        weak_echo_thres=weak_echo_thres,
        min_val_used=min_val_used,
        dB_averaging=dB_averaging,
        remove_small_objects=remove_small_objects,
        min_km2_size=min_km2_size,
        binary_close=binary_close,
        val_for_max_rad=val_for_max_rad,
        max_rad_km=max_rad_km,
        core_val=core_val,
        nosfcecho=nosfcecho,
        weakecho=weakecho,
        bkgd_val=bkgd_val,
        feat_val=feat_val,
        estimate_flag=estimate_flag,
        estimate_offset=estimate_offset,
    )
    result_dict = plugin(
        field_data,
        overest_field=overest_field,
        underest_field=underest_field,
    )
    if result_key:
        result = result_dict[result_key]
    else:
        result = xr.Dataset(result_dict)
    if output_path is not None:
        from radar_echo_classification.cli import save_echo_class_grid_to_netcdf

        save_echo_class_grid_to_netcdf(result, output_path)
    return result


class FeatureDetectionMainCli(CliBase):
    """``feature_detection_main`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/feature_detection_main.py"
    description = (
        "自适应阈值特征识别。\n"
        "必填路径由命令行传入。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/feature_detection_main.py --help\n"
        "  python cli/feature_detection_main.py --field-data-path PATH --output-path OUT.nc\n"
        "  python -m cli.feature_detection_main --field-data-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--field-data-path", required=True, metavar="PATH", help="主输入网格 NetCDF，通常为反射率。必填。")
        parser.add_argument("--overest-field-path", default=None, metavar="PATH", help="显式高估场。省略则按 estimate_offset 构造。")
        parser.add_argument("--underest-field-path", default=None, metavar="PATH", help="显式低估场。省略则按 estimate_offset 构造。")
        parser.add_argument("--dx", type=float, default=None, help="水平分辨率（米）。省略则自动估算。")
        parser.add_argument("--dy", type=float, default=None, help="水平分辨率（米）。省略则自动估算。")
        parser.add_argument("--level-m", dest="level_m", type=float, default=None, help="参与分类的高度（米）。省略则用第一层。")
        parser.add_argument("--always-core-thres", dest="always_core_thres", type=float, default=None, help="始终判为核心的阈值。省略则用 42。")
        parser.add_argument("--bkg-rad-km", dest="bkg_rad_km", type=float, default=None, help="背景半径（千米）。省略则用 11。")
        self.add_optional_bool(parser, "--use-cosine", help_true="使用余弦阈值关系。", help_false="不使用余弦阈值关系。省略则用函数默认值 true。")
        parser.add_argument("--max-diff", dest="max_diff", type=float, default=None, help="阈值关系 max_diff。省略则用 5。")
        parser.add_argument("--zero-diff-cos-val", dest="zero_diff_cos_val", type=float, default=None, help="zero_diff_cos_val。省略则用 55。")
        parser.add_argument("--scalar-diff", dest="scalar_diff", type=float, default=None, help="scalar_diff。省略则用 1.5。")
        self.add_optional_bool(parser, "--use-addition", help_true="使用加法形式的阈值关系。", help_false="不使用加法形式。省略则用函数默认值 true。")
        parser.add_argument("--calc-thres", dest="calc_thres", type=float, default=None, help="calc_thres。省略则用 0.75。")
        parser.add_argument("--weak-echo-thres", dest="weak_echo_thres", type=float, default=None, help="弱回波阈值。省略则用 5。")
        parser.add_argument("--min-val-used", dest="min_val_used", type=float, default=None, help="最小参与计算场值。省略则用 5。")
        self.add_optional_bool(parser, "--db-averaging", dest="dB_averaging", help_true="背景场按 dB 平均。", help_false="背景场不做 dB 平均。省略则用函数默认值 true。")
        self.add_optional_bool(parser, "--remove-small-objects", help_true="移除小目标。", help_false="保留小目标。省略则用函数默认值 true。")
        parser.add_argument("--min-km2-size", dest="min_km2_size", type=float, default=None, help="小目标面积阈值（平方千米）。省略则用 10。")
        self.add_optional_bool(parser, "--binary-close", help_true="做二值闭运算。", help_false="不做二值闭运算。省略则用函数默认值 false。")
        parser.add_argument("--val-for-max-rad", dest="val_for_max_rad", type=float, default=None, help="最大影响半径对应的场值。省略则用 30。")
        parser.add_argument("--max-rad-km", dest="max_rad_km", type=float, default=None, help="最大影响半径（千米）。省略则用 5。")
        parser.add_argument("--core-val", dest="core_val", type=int, default=None, help="核心类别编码。省略则用 3。")
        parser.add_argument("--nosfcecho", type=int, default=None, help="无回波类别编码。省略则用 0。")
        parser.add_argument("--weakecho", type=int, default=None, help="弱回波类别编码。省略则用 3。")
        parser.add_argument("--bkgd-val", dest="bkgd_val", type=int, default=None, help="背景类别编码。省略则用 1。")
        parser.add_argument("--feat-val", dest="feat_val", type=int, default=None, help="特征类别编码。省略则用 2。")
        self.add_optional_bool(parser, "--estimate-flag", help_true="计算高估/低估敏感性结果。", help_false="不计算敏感性结果。省略则用函数默认值 true。")
        parser.add_argument("--estimate-offset", dest="estimate_offset", type=float, default=None, help="构造高估/低估场的偏移。省略则用 5。")
        parser.add_argument("--result-key", default=None, help="只返回该字段，例如 feature_detection。省略则返回全部字段。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="结果 NetCDF。省略则只返回内存结果。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def feature_detection_main_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.feature_detection_main`` 都进这里。"""
    return FeatureDetectionMainCli().main(argv)


main = feature_detection_main_cli


if __name__ == "__main__":
    raise SystemExit(feature_detection_main_cli())
