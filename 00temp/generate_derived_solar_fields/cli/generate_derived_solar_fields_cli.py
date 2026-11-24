# -*- coding: utf-8 -*-
"""累计晴空太阳辐射。本包主入口。"""
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

from generate_derived_solar_fields.src.generate_derived_solar_fields import (
    GenerateClearskySolarRadiation,
)
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
    accumulation_period: int = None,
    surface_altitude_path=None,
    linke_turbidity_path=None,
    temporal_spacing: int = 30,
    new_title=None,
    output_path=None,
    config=None,
):
    """读取目标网格并累计晴空太阳辐射。``config`` 只换配置文件。"""
    _ = config
    if target_grid_path is None or not str(target_grid_path).strip():
        raise ValueError("缺少参数: target_grid_path")
    if accumulation_period is None:
        raise ValueError("缺少参数: accumulation_period")
    when = _as_datetime(time)
    target_grid = meb.read_griddata_from_nc(target_grid_path)
    surface_altitude = (
        meb.read_griddata_from_nc(surface_altitude_path)
        if surface_altitude_path and str(surface_altitude_path).strip()
        else None
    )
    linke_turbidity = (
        meb.read_griddata_from_nc(linke_turbidity_path)
        if linke_turbidity_path and str(linke_turbidity_path).strip()
        else None
    )
    result = GenerateClearskySolarRadiation().process(
        target_grid=target_grid,
        time=when,
        accumulation_period=int(accumulation_period),
        surface_altitude=surface_altitude,
        linke_turbidity=linke_turbidity,
        temporal_spacing=int(temporal_spacing),
        new_title=new_title,
    )
    if output_path:
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result
