#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""regrid 模块私有坐标与投影工具。"""

from __future__ import annotations

import json
from typing import Optional, Tuple

import numpy as np
import xarray as xr
from cf_units import Unit
from numpy import ndarray
from pyproj import CRS, Transformer

EARTH_RADIUS_M = 6378137.0


def parse_grid_mapping_attrs(attrs: dict) -> dict:
    """从 ``attrs['grid_mapping_attrs']`` JSON 字符串解析投影参数。"""
    grid_mapping_attrs = attrs.get("grid_mapping_attrs")
    if isinstance(grid_mapping_attrs, str) and grid_mapping_attrs.strip():
        try:
            parsed = json.loads(grid_mapping_attrs)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    return {}


def _is_distance_unit(unit: Optional[str]) -> bool:
    """判断单位是否为可换算到米的距离单位（非 degree）。"""
    text = (unit or "").strip().lower()
    if not text or "degree" in text:
        return False
    try:
        Unit(text).convert(1.0, Unit("m"))
        return True
    except Exception:
        return False


def is_projected_spatial(data: xr.DataArray) -> bool:
    """判断输入是否为投影坐标分支。

    判定依据：
    - lat/lon 坐标具有可换算为米的 units；或
    - attrs 中存在非 latitude_longitude 的 grid_mapping_attrs。

    若无米制 units、也无投影 grid_mapping_attrs，则视为经纬网格。
    """
    lat_units = data.coords["lat"].attrs.get("units") if "lat" in data.coords else None
    lon_units = data.coords["lon"].attrs.get("units") if "lon" in data.coords else None
    if _is_distance_unit(lat_units) and _is_distance_unit(lon_units):
        return True

    mapping = parse_grid_mapping_attrs(dict(data.attrs))
    if not mapping:
        return False
    grid_mapping_name = str(mapping.get("grid_mapping_name", "")).strip().lower()
    return bool(grid_mapping_name) and grid_mapping_name != "latitude_longitude"


def resolve_data_crs(data: xr.DataArray) -> CRS:
    """解析 DataArray 对应的 CRS。

    - 非投影（默认）：WGS84 经纬（EPSG:4326）
    - 投影：必须提供可解析的 ``grid_mapping_attrs``
    """
    if not is_projected_spatial(data):
        return CRS.from_epsg(4326)

    mapping = parse_grid_mapping_attrs(dict(data.attrs))
    if not mapping:
        raise ValueError(
            "投影坐标输入缺少可解析的 grid_mapping_attrs，无法确定坐标系。"
        )
    grid_mapping_name = str(mapping.get("grid_mapping_name", "")).strip().lower()
    if grid_mapping_name == "latitude_longitude":
        return CRS.from_epsg(4326)
    return CRS.from_cf(mapping)


def convert_axis_units_to_meters(
    values: ndarray, units: Optional[str], axis_name: str
) -> ndarray:
    """将投影坐标轴转换为米。"""
    if units is None:
        return np.asarray(values, dtype=np.float64)
    unit_text = str(units).strip()
    if not unit_text:
        return np.asarray(values, dtype=np.float64)
    try:
        return Unit(unit_text).convert(np.asarray(values, dtype=np.float64), Unit("m"))
    except Exception as err:
        raise ValueError(
            f"{axis_name} 坐标单位 {unit_text!r} 无法转换为米，请检查投影坐标单位。"
        ) from err


def spatial_axis_values(data: xr.DataArray, dim: str) -> ndarray:
    """返回空间坐标轴在其 CRS 下的数值。

    - 经纬：直接使用坐标值（度）
    - 投影：换算为米
    """
    values = np.asarray(data.coords[dim].values, dtype=np.float64)
    if not is_projected_spatial(data):
        return values
    units = data.coords[dim].attrs.get("units")
    return convert_axis_units_to_meters(values, units, dim)


def target_points_in_source_crs(
    source: xr.DataArray, target: xr.DataArray
) -> Tuple[ndarray, ndarray]:
    """将目标网格点变换到源场 CRS，返回 ``(sample_y, sample_x)`` 二维网格。

    插值在源场自己的规则坐标网（经纬或投影米制）上进行。
    """
    source_crs = resolve_data_crs(source)
    target_crs = resolve_data_crs(target)

    tgt_y = spatial_axis_values(target, "lat")
    tgt_x = spatial_axis_values(target, "lon")
    sample_y, sample_x = np.meshgrid(tgt_y, tgt_x, indexing="ij")

    if source_crs.equals(target_crs):
        return sample_y, sample_x

    # always_xy：输入/输出均为 (x/lon, y/lat)
    transformer = Transformer.from_crs(target_crs, source_crs, always_xy=True)
    sample_x, sample_y = transformer.transform(sample_x, sample_y)
    return np.asarray(sample_y, dtype=np.float64), np.asarray(sample_x, dtype=np.float64)


def estimate_grid_spacing_metres(data: xr.DataArray) -> float:
    """估算平均网格间距（米），用于邻域半径换算。"""
    lat_vals = np.asarray(data.coords["lat"].values, dtype=np.float64)
    lon_vals = np.asarray(data.coords["lon"].values, dtype=np.float64)
    if len(lat_vals) < 2 or len(lon_vals) < 2:
        return 1000.0

    lat_units = data.coords["lat"].attrs.get("units")
    lon_units = data.coords["lon"].attrs.get("units")
    if _is_distance_unit(lat_units) and _is_distance_unit(lon_units):
        lat_m = convert_axis_units_to_meters(lat_vals, lat_units, "lat")
        lon_m = convert_axis_units_to_meters(lon_vals, lon_units, "lon")
        return float(
            (np.mean(np.abs(np.diff(lat_m))) + np.mean(np.abs(np.diff(lon_m)))) / 2.0
        )

    # 经纬网格：用中心纬度近似米制格距
    mean_lat_rad = np.deg2rad(float(np.mean(lat_vals)))
    dy = np.mean(np.abs(np.diff(lat_vals))) * np.pi / 180.0 * EARTH_RADIUS_M
    dx = (
        np.mean(np.abs(np.diff(lon_vals)))
        * np.pi
        / 180.0
        * EARTH_RADIUS_M
        * np.cos(mean_lat_rad)
    )
    return float((dx + dy) / 2.0)


def distance_to_grid_cells(data: xr.DataArray, distance_m: float) -> int:
    """将米制半径换算为网格格点数（向下取整，至少为 1）。"""
    if distance_m <= 0:
        raise ValueError(
            f"Please specify a positive distance in metres. Distance of {distance_m}m"
        )
    spacing = estimate_grid_spacing_metres(data)
    cells = int(distance_m / abs(spacing))
    if cells == 0:
        raise ValueError(f"Distance of {distance_m}m gives zero cell extent")
    return cells
