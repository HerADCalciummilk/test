# -*- coding: utf-8 -*-
"""把已有层结递减率应用到温度场。"""
import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, _ROOT_DIR)
if _PARENT not in sys.path:
    sys.path.insert(1, _PARENT)

import numpy as np
import meteva_base as meb

from orographic_temperature_downscaling.src.lapse_rate import ApplyGriddedLapseRate
from utils.merge_params import merge_params


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


@merge_params()
def process(
    temperature_path: str = None,
    lapse_rate_path: str = None,
    source_orography_path: str = None,
    target_orography_path: str = None,
    output_path: str = None,
    config=None,
):
    """读四张场，调用 ``ApplyGriddedLapseRate.process``，按需写出。"""
    _ = config
    temperature_path = _need("temperature_path", temperature_path)
    lapse_rate_path = _need("lapse_rate_path", lapse_rate_path)
    source_orography_path = _need("source_orography_path", source_orography_path)
    target_orography_path = _need("target_orography_path", target_orography_path)
    _unbounded = (-np.inf, np.inf, np.nan)
    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )
    lapse_rate = meb.checkout_griddata(meb.read_griddata_from_nc(lapse_rate_path))
    source_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(source_orography_path), valid_val=_unbounded
    )
    target_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_orography_path), valid_val=_unbounded
    )
    if not meb.checkout_griddata_same_coords([temperature, lapse_rate], is_time_match=True):
        raise ValueError("层结递减率场与温度场的空间/时效坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, source_orography], is_time_match=False):
        raise ValueError("源地形高度场与温度场的坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, target_orography], is_time_match=False):
        raise ValueError("目标地形高度场与温度场的坐标不一致")
    result = ApplyGriddedLapseRate().process(
        temperature, lapse_rate, source_orography, target_orography
    )
    if output_path is not None and str(output_path).strip():
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)
    return result
