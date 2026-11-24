# -*- coding: utf-8 -*-
"""把地形增强场叠加或扣除到降水预报上。"""
import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _ROOT_DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

import meteva_base as meb
import numpy as np

from orographic_precipitation_downscaling.src.apply_orographic_enhancement import (
    ApplyOrographicEnhancement,
)
from utils.merge_params import merge_params

_UNBOUNDED = (-np.inf, np.inf, np.nan)


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


@merge_params()
def process(
    precip_path: str = None,
    orographic_enhancement_path: str = None,
    output_path: str = None,
    operation: str = "add",
    allowed_time_diff: int = 1800,
    config=None,
):
    """读降水和增强场，调用 ``ApplyOrographicEnhancement.process``，按需写出。"""
    _ = config
    precip_path = _need("precip_path", precip_path)
    orographic_enhancement_path = _need(
        "orographic_enhancement_path", orographic_enhancement_path
    )
    if not operation:
        operation = "add"
    if allowed_time_diff is None:
        allowed_time_diff = 1800
    precip = meb.checkout_griddata(
        meb.read_griddata_from_nc(precip_path), valid_val=_UNBOUNDED
    )
    orographic_enhancement = meb.checkout_griddata(
        meb.read_griddata_from_nc(orographic_enhancement_path), valid_val=_UNBOUNDED
    )
    result = ApplyOrographicEnhancement(operation).process(
        precip,
        orographic_enhancement,
        allowed_time_diff=allowed_time_diff,
    )
    if output_path is not None and str(output_path).strip():
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "precipitation"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")
    return result
