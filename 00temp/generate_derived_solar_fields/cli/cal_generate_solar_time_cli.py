# -*- coding: utf-8 -*-
"""地方太阳时。读目标网格，调用 ``GenerateSolarTime``。"""
from __future__ import annotations

import os
import sys
from datetime import datetime

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb

from generate_derived_solar_fields.src.generate_derived_solar_fields import GenerateSolarTime
from utils.merge_params import merge_params


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: time")
    text = str(value).strip()
    formats = (
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d%H",
        "%Y%m%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError("时间格式应为 YYYYMMDDHH、YYYYMMDDHHMM 或 YYYY-MM-DDTHH:MM:SS")


@merge_params()
def process(
    target_grid_path=None,
    time=None,
    new_title=None,
    output_path=None,
    config=None,
):
    """读取目标网格并计算地方太阳时。``config`` 只换配置文件。"""
    _ = config
    if target_grid_path is None or not str(target_grid_path).strip():
        raise ValueError("缺少参数: target_grid_path")
    target_grid = meb.read_griddata_from_nc(target_grid_path)
    result = GenerateSolarTime().process(
        target_grid=target_grid,
        time=_as_datetime(time),
        new_title=new_title,
    )
    if output_path:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result
