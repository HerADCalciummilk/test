# -*- coding: utf-8 -*-
"""地形带掩码。读地形与可选海陆掩码、阈值 JSON，调用 ``GenerateOrographyBandAncils``。"""
from __future__ import annotations

import json
import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb

from generate_ancillary.src.generate_ancillary import (
    THRESHOLDS_DICT,
    GenerateOrographyBandAncils,
)
from utils.merge_params import merge_params


@merge_params()
def process(
    orography_path=None,
    landmask_path=None,
    thresholds_path=None,
    output_path=None,
    config=None,
):
    """按海拔阈值生成地形带掩码。``config`` 只换配置文件。"""
    _ = config
    if orography_path is None or not str(orography_path).strip():
        raise ValueError("缺少参数: orography_path")
    orography = meb.read_griddata_from_nc(orography_path)
    if thresholds_path is None or not str(thresholds_path).strip():
        thresholds_dict = THRESHOLDS_DICT
    else:
        with open(thresholds_path, "r", encoding="utf-8") as input_file:
            thresholds_dict = json.load(input_file)
    landmask = (
        meb.read_griddata_from_nc(landmask_path)
        if landmask_path and str(landmask_path).strip()
        else None
    )
    result = GenerateOrographyBandAncils().process(
        orography=orography,
        thresholds_dict=thresholds_dict,
        landmask=landmask,
    )
    if output_path:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result
