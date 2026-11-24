# -*- coding: utf-8 -*-
"""地形风速降尺度。

``@merge_params`` 挂在 ``process`` 上。读入各场后调用 ``RoughnessCorrection.process`` 再写出。
"""
import os
import sys
import warnings
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

from orographic_wind_downscaling.src.wind_downscaling import (
    ABSOLUTE_CORRECTION_TOL,
    DX_MAX_FACTOR,
    DX_MIN_FACTOR,
    HREF_SCALE,
    RoughnessCorrection,
)
from utils.merge_params import merge_params


def _need(name, value):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError("缺少参数: %s" % name)
    return value


def _extract_height_level(data, output_height_level, output_height_level_units):
    """按指定高度提取单层结果。"""
    level_name = "level"
    if level_name not in data.coords:
        raise ValueError("结果中不存在 level 坐标。")
    levels = np.asarray(data.coords[level_name].values, dtype=np.float64)
    coord_units = data.coords[level_name].attrs.get("units", "m")
    target_level = float(output_height_level)
    if output_height_level_units and output_height_level_units != coord_units:
        from cf_units import Unit

        target_level = float(
            Unit(output_height_level_units).convert(target_level, Unit(coord_units))
        )
    idx = np.where(np.isclose(levels, target_level, rtol=0.0, atol=1e-6))[0]
    if idx.size == 0:
        raise ValueError(
            "Requested height level not found. "
            f"Available levels: {levels.tolist()} (units: {coord_units})"
        )
    return data.isel({level_name: int(idx[0])})


def _write_result_netcdf_float32(data, output_path):
    """以 float32 直写 NetCDF，避免 scale_factor 量化误差。"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    output = data.astype(np.float32, copy=False)
    var_name = output.name or "wind_speed"
    output.name = var_name
    dataset = output.to_dataset(name=var_name)
    dataset.to_netcdf(
        target,
        engine="netcdf4",
        encoding={
            var_name: {
                "dtype": "float32",
                "zlib": False,
                "_FillValue": np.float32(np.nan),
            }
        },
    )


@merge_params()
def process(
    wind_speed_path: str = None,
    sigma_path: str = None,
    target_orography_path: str = None,
    standard_orography_path: str = None,
    silhouette_roughness_path: str = None,
    model_resolution: float = None,
    vegetative_roughness_path: str = None,
    output_path: str = None,
    output_height_level: float = None,
    output_height_level_units: str = "m",
    absolute_correction_tol: float = None,
    href_scale: float = None,
    dx_max_factor: float = None,
    dx_min_factor: float = None,
    config=None,
):
    """读风速和粗糙度辅料，调用 ``RoughnessCorrection.process``，按需写出。"""
    _ = config
    wind_speed_path = _need("wind_speed_path", wind_speed_path)
    sigma_path = _need("sigma_path", sigma_path)
    target_orography_path = _need("target_orography_path", target_orography_path)
    standard_orography_path = _need("standard_orography_path", standard_orography_path)
    silhouette_roughness_path = _need("silhouette_roughness_path", silhouette_roughness_path)
    if model_resolution is None:
        raise ValueError("缺少参数: model_resolution")

    _unbounded = (-np.inf, np.inf, np.nan)
    if output_height_level_units and output_height_level is None:
        warnings.warn(
            "output_height_level_units 已设置，但未提供 output_height_level；该参数不会生效。"
        )

    wind_speed = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_speed_path), valid_val=_unbounded
    )
    sigma = meb.checkout_griddata(
        meb.read_griddata_from_nc(sigma_path), is_single=True, valid_val=_unbounded
    )
    target_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    standard_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(standard_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    silhouette_roughness = meb.checkout_griddata(
        meb.read_griddata_from_nc(silhouette_roughness_path), is_single=True
    )
    vegetative_roughness = (
        None
        if vegetative_roughness_path is None or not str(vegetative_roughness_path).strip()
        else meb.checkout_griddata(
            meb.read_griddata_from_nc(vegetative_roughness_path), is_single=True
        )
    )
    plugin = RoughnessCorrection(
        silhouette_roughness,
        sigma,
        target_orography,
        standard_orography,
        float(model_resolution),
        z0=vegetative_roughness,
        absolute_correction_tol=(
            ABSOLUTE_CORRECTION_TOL
            if absolute_correction_tol is None
            else float(absolute_correction_tol)
        ),
        href_scale=HREF_SCALE if href_scale is None else float(href_scale),
        dx_max_factor=DX_MAX_FACTOR if dx_max_factor is None else float(dx_max_factor),
        dx_min_factor=DX_MIN_FACTOR if dx_min_factor is None else float(dx_min_factor),
    )
    result, _hc_add = plugin.process(wind_speed)
    result = result.astype(np.float32, copy=False)
    result.name = wind_speed.name or result.name or "wind_speed"
    if output_height_level is not None:
        result = _extract_height_level(
            result,
            output_height_level=output_height_level,
            output_height_level_units=output_height_level_units,
        )
    if output_path is not None and str(output_path).strip():
        _write_result_netcdf_float32(result, output_path)
    return result
