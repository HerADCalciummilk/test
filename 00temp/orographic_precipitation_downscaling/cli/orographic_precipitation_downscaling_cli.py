# -*- coding: utf-8 -*-
"""按多个尺度做地形降水降尺度。

``@merge_params`` 挂在 ``process`` 上：读场、调用级联插件、写出。
"""
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
import xarray as xr

from orographic_precipitation_downscaling.src.cascade_orographic_downscaling import (
    CascadeOrographicDownscaling,
)
from utils.merge_params import merge_params

_UNBOUNDED = (-np.inf, np.inf, np.nan)


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


def _ensure_units(data: xr.DataArray, fallback: str) -> xr.DataArray:
    units = str(data.attrs.get("units") or "").strip()
    if not units:
        data.attrs["units"] = fallback
    if data.attrs.get("units") == "m s**-1":
        data.attrs["units"] = "m s-1"
    return data


def _read_field(path: str, fallback_unit: str, *, single: bool = False) -> xr.DataArray:
    data = meb.checkout_griddata(
        meb.read_griddata_from_nc(path),
        is_single=single,
        valid_val=_UNBOUNDED,
    )
    return _ensure_units(data, fallback_unit)


@merge_params()
def process(
    precip_path: str = None,
    temperature_path: str = None,
    humidity_path: str = None,
    pressure_path: str = None,
    uwind_path: str = None,
    vwind_path: str = None,
    orography_model_path: str = None,
    orography_target_path: str = None,
    stages: str = None,
    output_path: str = None,
    zero_below: float = None,
    wet_threshold: float = 0.1,
    config=None,
):
    """读一个时次的降水与温湿压风、两张地形，调用级联插件，按需写出。"""
    _ = config
    precip_path = _need("precip_path", precip_path)
    temperature_path = _need("temperature_path", temperature_path)
    humidity_path = _need("humidity_path", humidity_path)
    pressure_path = _need("pressure_path", pressure_path)
    uwind_path = _need("uwind_path", uwind_path)
    vwind_path = _need("vwind_path", vwind_path)
    orography_model_path = _need("orography_model_path", orography_model_path)
    orography_target_path = _need("orography_target_path", orography_target_path)
    stages = _need("stages", stages)
    temperature = _read_field(temperature_path, "degC")
    humidity = _read_field(humidity_path, "%")
    pressure = _read_field(pressure_path, "Pa")
    uwind = _read_field(uwind_path, "m s-1")
    vwind = _read_field(vwind_path, "m s-1")
    precip = _read_field(precip_path, "mm h-1")
    orography_model = _read_field(orography_model_path, "m", single=True)
    orography_target = _read_field(orography_target_path, "m", single=True)
    result = CascadeOrographicDownscaling().process(
        precip,
        temperature,
        humidity,
        pressure,
        uwind,
        vwind,
        orography_model,
        orography_target,
        stages=stages,
        zero_below=zero_below,
        wet_threshold=wet_threshold,
    )
    if output_path is not None and str(output_path).strip():
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "precipitation_rate"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")
    return result
