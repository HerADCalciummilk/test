#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""grid_mapping 元数据读取与投影坐标转换。"""

from __future__ import annotations

import json

import numpy as np
import xarray as xr
from cf_units import Unit
from pyproj import CRS, Transformer


def _get_projection_attrs(target_grid: xr.DataArray) -> dict:
    """从 ``attrs['grid_mapping_attrs']`` JSON 字符串解析投影参数。"""
    grid_mapping_attrs = target_grid.attrs.get("grid_mapping_attrs")
    if isinstance(grid_mapping_attrs, str) and grid_mapping_attrs.strip():
        try:
            parsed = json.loads(grid_mapping_attrs)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    return {}


def _convert_axis_units_to_meters(values: np.ndarray, units: str | None, axis_name: str) -> np.ndarray:
    """将投影坐标轴转换为米，保持与原算法行为一致。"""
    if units is None:
        return values
    unit_text = str(units).strip()
    if not unit_text:
        return values
    try:
        source_unit = Unit(unit_text)
        target_unit = Unit("m")
        return source_unit.convert(values, target_unit)
    except Exception as err:
        raise ValueError(
            f"{axis_name} 坐标单位 {unit_text!r} 无法转换为米，请检查投影坐标单位。"
        ) from err


def extract_lat_lon_mesh(target_grid: xr.DataArray) -> tuple[np.ndarray, np.ndarray]:
    """从六维网格中提取经纬度二维网格。

    默认将 ``lat``/``lon`` 视为经纬度。仅当提供 ``attrs['grid_mapping_attrs']``
    且 ``grid_mapping_name`` 不是 ``latitude_longitude`` 时，才按投影参数转换。
    """
    lat_like = np.asarray(target_grid.coords["lat"].values, dtype=np.float64)
    lon_like = np.asarray(target_grid.coords["lon"].values, dtype=np.float64)
    lat_like_2d, lon_like_2d = np.meshgrid(lat_like, lon_like, indexing="ij")

    projection_attrs = _get_projection_attrs(target_grid)
    # 未提供投影元数据时，默认按经纬坐标处理
    if not projection_attrs:
        return lat_like_2d.astype(np.float32), lon_like_2d.astype(np.float32)

    grid_mapping_name = str(projection_attrs.get("grid_mapping_name", "")).strip().lower()
    if not grid_mapping_name:
        raise ValueError("grid_mapping_attrs 中缺少 grid_mapping_name，无法识别投影坐标类型。")
    if grid_mapping_name == "latitude_longitude":
        return lat_like_2d.astype(np.float32), lon_like_2d.astype(np.float32)

    # 投影坐标：单位换算到米后转到 WGS84 经纬度
    lat_units = target_grid.coords["lat"].attrs.get("units")
    lon_units = target_grid.coords["lon"].attrs.get("units")
    lat_like_2d = _convert_axis_units_to_meters(lat_like_2d, lat_units, "lat")
    lon_like_2d = _convert_axis_units_to_meters(lon_like_2d, lon_units, "lon")
    source_crs = CRS.from_cf(projection_attrs)
    transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
    lons_2d, lats_2d = transformer.transform(lon_like_2d, lat_like_2d)
    return lats_2d.astype(np.float32), lons_2d.astype(np.float32)
