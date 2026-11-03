#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""特征识别 CLI 示例脚本。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import meteva_base as meb
import xarray as xr


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
    output_path: Optional[str] = None,
) -> xr.DataArray | xr.Dataset:
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


if __name__ == "__main__":
    import sys

    # 添加项目根目录到 Python 路径
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    data_dir = Path(__file__).resolve().parents[1] / "test_data" / "echo_class" / "cli_input"
    output_dir = Path(__file__).resolve().parents[1] / "test_data" / "echo_class" / "cli_output"

    process(
        str(data_dir / "ACHN_CREF000_20240612_070000_small.nc"),
        level_m=0.0,
        result_key="feature_detection",
        output_path=str(output_dir / "achn_feature_cli.nc"),
    )
