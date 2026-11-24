# -*- coding: utf-8 -*-
"""用已有 U/V 计算地形增强。"""
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

from orographic_precipitation_downscaling.src.orographic_enhancement import (
    OrographicEnhancement,
)
from utils.merge_params import merge_params

_UNBOUNDED = (-np.inf, np.inf, np.nan)


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


@merge_params()
def process(
    temperature_path: str = None,
    humidity_path: str = None,
    pressure_path: str = None,
    uwind_path: str = None,
    vwind_path: str = None,
    orography_path: str = None,
    output_path: str = None,
    config=None,
):
    """读温湿压、U/V 和地形，调用 ``OrographicEnhancement.process``，按需写出。"""
    _ = config
    temperature_path = _need("temperature_path", temperature_path)
    humidity_path = _need("humidity_path", humidity_path)
    pressure_path = _need("pressure_path", pressure_path)
    uwind_path = _need("uwind_path", uwind_path)
    vwind_path = _need("vwind_path", vwind_path)
    orography_path = _need("orography_path", orography_path)
    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_UNBOUNDED
    )
    humidity = meb.checkout_griddata(
        meb.read_griddata_from_nc(humidity_path), valid_val=_UNBOUNDED
    )
    pressure = meb.checkout_griddata(
        meb.read_griddata_from_nc(pressure_path), valid_val=_UNBOUNDED
    )
    uwind = meb.checkout_griddata(meb.read_griddata_from_nc(uwind_path), valid_val=_UNBOUNDED)
    vwind = meb.checkout_griddata(meb.read_griddata_from_nc(vwind_path), valid_val=_UNBOUNDED)
    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=_UNBOUNDED,
    )
    for label, field in (
        ("相对湿度场", humidity),
        ("气压场", pressure),
        ("东西风场", uwind),
        ("南北风场", vwind),
    ):
        if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")
    result = OrographicEnhancement().process(
        temperature, humidity, pressure, uwind, vwind, orography
    )
    if output_path is not None and str(output_path).strip():
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "orographic_enhancement"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")
    return result
