# -*- coding: utf-8 -*-
"""由高分辨率地形和模式地形计算 sigma 与轮廓粗糙度。"""
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

import numpy as np
import xarray as xr
import meteva_base as meb

from orographic_wind_downscaling.src.roughness import RoughnessCalculation
from utils.merge_params import merge_params


def _need(name, value):
    if value is None or not str(value).strip():
        raise ValueError("缺少参数: %s" % name)
    return value


def _write(data: xr.DataArray, output_path: str) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    name = data.name or "roughness"
    data.name = name
    data.astype(np.float32, copy=False).to_dataset(name=name).to_netcdf(target)


@merge_params()
def process(
    orography_path: str = None,
    sigma_output_path: str = None,
    silhouette_output_path: str = None,
    model_orography_path: str = None,
    output_path: str = None,
    config=None,
):
    """读两张地形，调用 ``RoughnessCalculation.process``，按需写出 sigma 与轮廓粗糙度。"""
    _ = config
    orography_path = _need("orography_path", orography_path)
    model_orography_path = _need("model_orography_path", model_orography_path)
    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    model_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(model_orography_path),
        is_single=True,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    sigma, silhouette = RoughnessCalculation().process(orography, model_orography)
    if sigma_output_path is not None and str(sigma_output_path).strip():
        _write(sigma, sigma_output_path)
    if silhouette_output_path is not None and str(silhouette_output_path).strip():
        _write(silhouette, silhouette_output_path)
    if output_path is not None and str(output_path).strip() and not sigma_output_path:
        _write(sigma, output_path)
    return sigma, silhouette
