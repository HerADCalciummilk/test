# -*- coding: utf-8 -*-
"""地形平滑系数。读地形与可选掩码，调用 ``OrographicSmoothingCoefficients``，按需写出 x/y 两场。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb

from generate_orographic_smoothing_coefficients.src.generate_orographic_smoothing_coefficients import (
    OrographicSmoothingCoefficients,
)
from utils.merge_params import merge_params


def paired_output_paths(output_path):
    """由 ``output_path`` 推导 x/y 两个单场路径。"""
    path = Path(output_path)
    return (
        path.with_name("%s_x%s" % (path.stem, path.suffix)),
        path.with_name("%s_y%s" % (path.stem, path.suffix)),
    )


@merge_params()
def process(
    orography_path=None,
    mask_path=None,
    min_gradient_smoothing_coefficient: float = 0.5,
    max_gradient_smoothing_coefficient: float = 0.0,
    power: float = 1.0,
    use_mask_boundary: bool = False,
    invert_mask: bool = False,
    output_path=None,
    config=None,
):
    """读取地形（及可选掩码）并生成 x/y 平滑系数。``config`` 只换配置文件。"""
    _ = config
    if orography_path is None or not str(orography_path).strip():
        raise ValueError("缺少参数: orography_path")
    orography = meb.read_griddata_from_nc(orography_path)
    mask = (
        meb.read_griddata_from_nc(mask_path)
        if mask_path and str(mask_path).strip()
        else None
    )
    coeff_x, coeff_y = OrographicSmoothingCoefficients(
        min_gradient_smoothing_coefficient=min_gradient_smoothing_coefficient,
        max_gradient_smoothing_coefficient=max_gradient_smoothing_coefficient,
        power=power,
        use_mask_boundary=use_mask_boundary,
        invert_mask=invert_mask,
    ).process(orography, mask=mask)
    if output_path:
        path_x, path_y = paired_output_paths(output_path)
        path_x.parent.mkdir(parents=True, exist_ok=True)
        meb.write_griddata_to_nc(coeff_x.astype("float32"), str(path_x), creat_dir=True)
        meb.write_griddata_to_nc(coeff_y.astype("float32"), str(path_y), creat_dir=True)
    return coeff_x, coeff_y
