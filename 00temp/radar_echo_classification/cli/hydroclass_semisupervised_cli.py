#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""半监督水凝物分类命令行。

在本包目录执行::

    python cli/hydroclass_semisupervised_main.py --refl-path PATH [--output-path PATH]
    python -m cli.hydroclass_semisupervised_main --refl-path PATH

Python::

    from cli.hydroclass_semisupervised_main import HydroclassSemisupervisedMainCli
    HydroclassSemisupervisedMainCli.call(refl_path="PATH")
"""

from __future__ import annotations

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

from utils.merge_params import merge_params
from utils.conf_ini import overlay_none


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


@merge_params()
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
    output_path: Optional[str] = None, config=None) -> xr.DataArray | xr.Dataset:
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
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "refl_path": (refl_path, "str"),
        "zdr_path": (zdr_path, "str"),
        "rhv_path": (rhv_path, "str"),
        "kdp_path": (kdp_path, "str"),
        "temp_path": (temp_path, "str"),
        "iso0_path": (iso0_path, "str"),
        "mass_centers_path": (mass_centers_path, "str"),
        "radar_freq": (radar_freq, "float"),
        "result_key": (result_key, "str"),
        "output_path": (output_path, "str"),
    })
    refl_path = _over['refl_path']
    zdr_path = _over['zdr_path']
    rhv_path = _over['rhv_path']
    kdp_path = _over['kdp_path']
    temp_path = _over['temp_path']
    iso0_path = _over['iso0_path']
    mass_centers_path = _over['mass_centers_path']
    radar_freq = _over['radar_freq']
    result_key = _over['result_key']
    output_path = _over['output_path']
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
