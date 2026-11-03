#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""半监督水凝物分类 CLI 示例脚本。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import numpy as np
import xarray as xr


def _read_mass_centers(path: Optional[str]) -> np.ndarray | None:
    """读取水凝物分类质心文件。"""
    if path is None:
        return None

    file_path = Path(path)
    if file_path.suffix.lower() == ".npy":
        return np.load(file_path)

    try:
        return np.loadtxt(file_path, delimiter=",")
    except ValueError:
        return np.loadtxt(file_path)


def process(
    *,
    refl_path: str = None,
    zdr_path: str = None,
    rhv_path: str = None,
    kdp_path: str = None,
    temp_path: str = None,
    iso0_path: str = None,
    hydro_names: Sequence[str] = ("AG", "CR", "LR", "RP", "RN", "VI", "WS", "MH", "IH/HDG"),
    var_names: Sequence[str] = ("Zh", "ZDR", "KDP", "RhoHV", "relH"),
    mass_centers_path: str = None,
    weights: Sequence[float] = (1.0, 1.0, 1.0, 0.75, 0.5),
    value: float = 50.0,
    lapse_rate: float = -6.5,
    radar_freq: float = None,
    temp_ref: str = "temperature",
    compute_entropy: bool = False,
    output_distances: bool = False,
    vectorize: bool = False,
    result_key: str = None,
    output_path: Optional[str] = None,
) -> xr.DataArray | xr.Dataset:
    """使用半监督分类方法识别雷达体积中的水凝物类别。

    参数
    ----
    refl_path, zdr_path, rhv_path, kdp_path : str, optional
        反射率、差分反射率、相关系数和比差分相移率网格文件路径；是否必需
        由 ``var_names`` 决定。
    temp_path, iso0_path : str, optional
        温度场或相对零度层高度场文件路径。``var_names`` 包含 ``relH`` 时，
        按 ``temp_ref`` 选择所需输入。
    hydro_names : sequence of str, optional
        输出水凝物类别名称序列。
    var_names : sequence of str, optional
        参与分类的变量及顺序，可选 ``Zh``、``ZDR``、``KDP``、``RhoHV``、
        ``relH``。
    mass_centers_path : str, optional
        质心文件路径，支持 ``.npy``、逗号分隔文本及普通文本；为空时按
        输入网格 ``frequency`` 属性或 ``radar_freq`` 选择默认频段质心。
    weights : sequence of float, optional
        各分类变量的距离权重，顺序须与 ``var_names`` 一致。
    value : float, optional
        距离转换为类别比例时使用的衰减控制参数。
    lapse_rate : float, optional
        由温度计算相对零度层高度时的温度垂直递减率。
    radar_freq : float, optional
        雷达频率，单位 Hz；仅在未提供质心且输入网格无 ``frequency`` 属性时
        用于选择默认质心。
    temp_ref : str, optional
        温度相关输入解释方式，可选 ``temperature`` 或
        ``height_over_iso0``。
    compute_entropy : bool, optional
        是否额外输出水凝物分类熵场。
    output_distances : bool, optional
        是否额外输出各水凝物类别比例场。
    vectorize : bool, optional
        是否使用向量化距离分类路径。
    result_key : str, optional
        指定时仅返回对应结果字段，例如 ``hydro``；为空时返回含所有字段的
        ``xr.Dataset``。
    output_path : str, optional
        结果 NetCDF 输出路径；为空时仅返回内存结果。

    返回
    ----
    xr.DataArray or xr.Dataset
        ``result_key`` 被指定时为对应结果场；否则为至少含 ``hydro`` 的
        数据集，并按 ``compute_entropy``、``output_distances`` 包含可选字段。
    """
    from radar_echo_classification.src.echo_class import HydroclassSemisupervisedPlugin

    refl = meb.read_griddata_from_nc(refl_path) if refl_path is not None else None
    zdr = meb.read_griddata_from_nc(zdr_path) if zdr_path is not None else None
    rhv = meb.read_griddata_from_nc(rhv_path) if rhv_path is not None else None
    kdp = meb.read_griddata_from_nc(kdp_path) if kdp_path is not None else None
    temp = meb.read_griddata_from_nc(temp_path) if temp_path is not None else None
    iso0 = meb.read_griddata_from_nc(iso0_path) if iso0_path is not None else None
    plugin = HydroclassSemisupervisedPlugin(
        hydro_names=tuple(hydro_names),
        var_names=tuple(var_names),
        mass_centers=_read_mass_centers(mass_centers_path),
        weights=np.asarray(weights, dtype=np.float32),
        value=value,
        lapse_rate=lapse_rate,
        radar_freq=radar_freq,
        temp_ref=temp_ref,
        compute_entropy=compute_entropy,
        output_distances=output_distances,
        vectorize=vectorize,
    )
    result_dict = plugin(
        refl=refl,
        zdr=zdr,
        rhv=rhv,
        kdp=kdp,
        temp=temp,
        iso0=iso0,
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
        refl_path=str(data_dir / "hydro_corrected_reflectivity.nc"),
        zdr_path=str(data_dir / "hydro_corrected_differential_reflectivity.nc"),
        kdp_path=str(data_dir / "hydro_specific_differential_phase.nc"),
        rhv_path=str(data_dir / "hydro_uncorrected_cross_correlation_ratio.nc"),
        temp_path=str(data_dir / "hydro_temperature.nc"),
        output_path=str(output_dir / "hydroclass_cli.nc"),
    )
