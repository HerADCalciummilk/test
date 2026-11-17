#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试辅助：合成场与数值对比。"""

from __future__ import annotations

import numpy as np
import xarray as xr
import meteva_base as meb


def to_compare_array(data) -> np.ndarray:
    """统一对比数组形状（去掉长度为 1 的维）。

    支持迁移版 ``xr.DataArray``、官方 / 原 CLI 的 iris Cube，以及 ndarray。
    """
    if isinstance(data, xr.DataArray):
        arr = np.asarray(data.values, dtype=np.float64)
    elif hasattr(data, "data"):
        # iris Cube 等
        arr = np.asarray(data.data, dtype=np.float64)
    else:
        arr = np.asarray(data, dtype=np.float64)
    return np.squeeze(arr)


def make_meb6d(
    data_2d: np.ndarray,
    *,
    lats: np.ndarray,
    lons: np.ndarray,
    name: str = "air_temperature",
    units: str = "K",
    lat_units: str | None = None,
    lon_units: str | None = None,
    grid_mapping_attrs: str | None = None,
    attrs: dict | None = None,
) -> xr.DataArray:
    """由二维场构造标准六维 meb DataArray。"""
    values = np.asarray(data_2d, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError(f"make_meb6d 仅支持二维输入，收到 shape={values.shape}")
    if values.shape != (len(lats), len(lons)):
        raise ValueError(
            f"data shape {values.shape} 与 lat/lon 长度 {(len(lats), len(lons))} 不一致"
        )

    lat_attrs = {}
    lon_attrs = {}
    if lat_units is not None:
        lat_attrs["units"] = lat_units
    if lon_units is not None:
        lon_attrs["units"] = lon_units

    out_attrs = {"units": units}
    if attrs:
        out_attrs.update(attrs)
    if grid_mapping_attrs is not None:
        out_attrs["grid_mapping_attrs"] = grid_mapping_attrs

    da = xr.DataArray(
        values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :],
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array([0], dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array(
                [np.datetime64("1970-01-01T00:00:00")], dtype="datetime64[ns]"
            ),
            "dtime": np.array([0], dtype=np.int32),
            "lat": xr.DataArray(
                np.asarray(lats, dtype=np.float32), dims=("lat",), attrs=lat_attrs
            ),
            "lon": xr.DataArray(
                np.asarray(lons, dtype=np.float32), dims=("lon",), attrs=lon_attrs
            ),
        },
        name=name,
        attrs=out_attrs,
    )
    meb.set_griddata_attrs(
        da,
        units=da.attrs.get("units"),
        model_var=da.attrs.get("model_var"),
        dtime_units=da.attrs.get("dtime_units"),
        level_type=da.attrs.get("level_type"),
        time_type=da.attrs.get("time_type"),
        time_bounds=da.attrs.get("time_bounds"),
        is_default=True,
    )
    return da
