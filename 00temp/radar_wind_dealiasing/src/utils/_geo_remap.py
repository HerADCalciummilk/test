#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""区域退模糊插件使用的门点地理坐标与规则经纬重映射工具。"""

from __future__ import annotations

import cf_units
import numpy as np
import xarray as xr
from scipy.interpolate import griddata

import meteva_base as meb


EARTH_RADIUS_METERS = 6370997.0


def _unit_scale_to_meters(unit_value: str | None):
    """根据单位字符串返回到米的缩放系数。"""
    if unit_value is None:
        return None

    try:
        src_unit = cf_units.Unit(str(unit_value).strip())
        dst_unit = cf_units.Unit("m")
        return float(src_unit.convert(1.0, dst_unit))
    except Exception:
        return None


def _axis_to_meters(values: np.ndarray, unit_value: str | None):
    """将已知单位的一维坐标轴转换为米。"""
    scale = _unit_scale_to_meters(unit_value)
    if scale is None:
        return None
    return np.asarray(values, dtype=np.float64) * scale


def polar_to_lonlat(
    radar_lon: float,
    radar_lat: float,
    azimuth_deg,
    range_m,
    elevation_deg: float = 0.0,
):
    """将极坐标门点位置转换为经纬度门点坐标。"""
    azimuth = np.asarray(azimuth_deg, dtype=np.float64)
    radial_range = np.asarray(range_m, dtype=np.float64)

    if azimuth.ndim != 1:
        raise ValueError("azimuth_deg must be a 1D sequence")
    if radial_range.ndim != 1:
        raise ValueError("range_m must be a 1D sequence")

    azimuth_rad = np.deg2rad(azimuth)
    elevation_rad = np.deg2rad(float(elevation_deg))
    range_2d = np.broadcast_to(
        radial_range.reshape(1, -1),
        (azimuth.size, radial_range.size),
    )
    azimuth_2d = np.broadcast_to(
        azimuth_rad.reshape(-1, 1),
        range_2d.shape,
    )

    ground_range = range_2d * np.cos(elevation_rad)
    x = ground_range * np.sin(azimuth_2d)
    y = ground_range * np.cos(azimuth_2d)

    lon0 = np.deg2rad(float(radar_lon))
    lat0 = np.deg2rad(float(radar_lat))
    rho = np.sqrt(x * x + y * y)
    c = rho / EARTH_RADIUS_METERS

    sin_c = np.sin(c)
    cos_c = np.cos(c)
    sin_lat0 = np.sin(lat0)
    cos_lat0 = np.cos(lat0)
    gate_lat_rad = np.empty_like(rho, dtype=np.float64)
    gate_lon_rad = np.empty_like(rho, dtype=np.float64)

    zero_mask = rho == 0.0
    nonzero_mask = ~zero_mask
    gate_lat_rad[zero_mask] = lat0
    gate_lon_rad[zero_mask] = lon0

    if np.any(nonzero_mask):
        rho_nz = rho[nonzero_mask]
        x_nz = x[nonzero_mask]
        y_nz = y[nonzero_mask]
        sin_c_nz = sin_c[nonzero_mask]
        cos_c_nz = cos_c[nonzero_mask]

        gate_lat_rad[nonzero_mask] = np.arcsin(
            cos_c_nz * sin_lat0
            + (y_nz * sin_c_nz * cos_lat0 / rho_nz)
        )
        gate_lon_rad[nonzero_mask] = lon0 + np.arctan2(
            x_nz * sin_c_nz,
            rho_nz * cos_lat0 * cos_c_nz
            - y_nz * sin_lat0 * sin_c_nz,
        )

    return np.rad2deg(gate_lon_rad), np.rad2deg(gate_lat_rad)


def attach_gate_lonlat(
    grid_data: xr.DataArray,
    radar_lon: float,
    radar_lat: float,
    azimuth_deg=None,
    range_m=None,
    elevation_deg: float = 0.0,
    gate_lon_name: str = "gate_lon",
    gate_lat_name: str = "gate_lat",
) -> xr.DataArray:
    """为极坐标体扫附加二维门点经纬度坐标。"""
    # 不做 ±1000 截断：退模糊结果常含 _FillValue=-9999，截断会误警并改值。
    normalized = meb.checkout_griddata(
        grid_data,
        is_single=False,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    if azimuth_deg is None:
        azimuth = (
            normalized.coords["azimuth"].values
            if "azimuth" in normalized.coords
            else normalized.lat.values
        )
    else:
        azimuth = azimuth_deg

    if range_m is None:
        if "range" in normalized.coords:
            range_axis = normalized.coords["range"]
            range_values = range_axis.values
            range_unit = getattr(range_axis, "attrs", {}).get("units")
        else:
            range_values = normalized.lon.values
            range_unit = (
                normalized.attrs.get("range_units")
                or getattr(normalized.lon, "attrs", {}).get("units")
                or normalized.attrs.get("lon_units")
            )
        radial_range = _axis_to_meters(range_values, range_unit)
        if radial_range is None:
            range_scale = normalized.attrs.get("range_scale_to_m")
            try:
                range_scale = (
                    float(range_scale)
                    if range_scale is not None
                    else None
                )
            except (TypeError, ValueError):
                range_scale = None
            if range_scale is not None and np.isfinite(range_scale):
                radial_range = (
                    np.asarray(range_values, dtype=np.float64)
                    * range_scale
                )
            else:
                radial_range = range_values
    else:
        radial_range = range_m

    gate_lon, gate_lat = polar_to_lonlat(
        radar_lon=radar_lon,
        radar_lat=radar_lat,
        azimuth_deg=azimuth,
        range_m=radial_range,
        elevation_deg=elevation_deg,
    )
    return normalized.copy().assign_coords(
        {
            gate_lon_name: (
                ("lat", "lon"),
                gate_lon.astype(np.float64, copy=False),
            ),
            gate_lat_name: (
                ("lat", "lon"),
                gate_lat.astype(np.float64, copy=False),
            ),
        }
    )


def infer_radar_location_from_attrs(grid_data: xr.DataArray):
    """从网格属性推断雷达站点经纬度。"""
    attr_pairs = (
        ("radar_lon", "radar_lat"),
        ("site_lon", "site_lat"),
        ("longitude", "latitude"),
    )
    for lon_key, lat_key in attr_pairs:
        if lon_key in grid_data.attrs and lat_key in grid_data.attrs:
            try:
                return (
                    float(grid_data.attrs[lon_key]),
                    float(grid_data.attrs[lat_key]),
                )
            except (TypeError, ValueError):
                continue
    return None, None


def _haversine_distance_m(lon1, lat1, lon2, lat2):
    """计算球面两点之间的大圆距离，单位为米。"""
    lon1_rad = np.deg2rad(np.asarray(lon1, dtype=np.float64))
    lat1_rad = np.deg2rad(np.asarray(lat1, dtype=np.float64))
    lon2_rad = np.deg2rad(np.asarray(lon2, dtype=np.float64))
    lat2_rad = np.deg2rad(np.asarray(lat2, dtype=np.float64))

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad)
        * np.cos(lat2_rad)
        * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def mask_outside_radar_coverage(
    data_2d,
    target_lon,
    target_lat,
    radar_lon: float,
    radar_lat: float,
    gate_lon,
    gate_lat,
    coverage_radius_m: float | None = None,
    fill_value=np.nan,
) -> np.ndarray:
    """将雷达圆形覆盖范围外的规则经纬网格置为缺测。"""
    values = np.asarray(data_2d, dtype=np.float32).copy()
    lon_axis = np.asarray(target_lon, dtype=np.float64)
    lat_axis = np.asarray(target_lat, dtype=np.float64)
    gate_lon_2d = np.asarray(gate_lon, dtype=np.float64)
    gate_lat_2d = np.asarray(gate_lat, dtype=np.float64)

    valid_mask = np.isfinite(gate_lon_2d) & np.isfinite(gate_lat_2d)
    if not np.any(valid_mask):
        return values

    if coverage_radius_m is None:
        coverage_radius_m = float(
            np.nanmax(
                _haversine_distance_m(
                    radar_lon,
                    radar_lat,
                    gate_lon_2d[valid_mask],
                    gate_lat_2d[valid_mask],
                )
            )
        )

    target_lon_2d, target_lat_2d = np.meshgrid(lon_axis, lat_axis)
    target_distance_m = _haversine_distance_m(
        radar_lon,
        radar_lat,
        target_lon_2d,
        target_lat_2d,
    )
    values[target_distance_m > coverage_radius_m] = fill_value
    return values


def remap_gate_data_to_latlon_grid(
    values,
    gate_lon,
    gate_lat,
    target_lon,
    target_lat,
    method: str = "nearest",
    missing_value=None,
    fill_value=np.nan,
) -> np.ndarray:
    """将雷达门点场插值到规则经纬网格。"""
    supported_methods = {"nearest", "linear"}
    if method not in supported_methods:
        raise ValueError(
            f"method must be one of {supported_methods}, got {method!r}"
        )

    if np.ma.isMaskedArray(values):
        values_2d = np.asarray(
            np.ma.filled(values, np.nan),
            dtype=np.float64,
        )
    else:
        values_2d = np.asarray(values, dtype=np.float64)
    gate_lon_2d = np.asarray(gate_lon, dtype=np.float64)
    gate_lat_2d = np.asarray(gate_lat, dtype=np.float64)
    target_lon_1d = np.asarray(target_lon, dtype=np.float64)
    target_lat_1d = np.asarray(target_lat, dtype=np.float64)

    if (
        values_2d.shape != gate_lon_2d.shape
        or values_2d.shape != gate_lat_2d.shape
    ):
        raise ValueError(
            "values, gate_lon, and gate_lat must have the same 2D shape"
        )
    if target_lon_1d.ndim != 1 or target_lat_1d.ndim != 1:
        raise ValueError("target_lon and target_lat must be 1D sequences")

    valid_mask = (
        np.isfinite(values_2d)
        & np.isfinite(gate_lon_2d)
        & np.isfinite(gate_lat_2d)
    )
    try:
        fill_value_f = float(fill_value)
    except (TypeError, ValueError):
        fill_value_f = None
    if fill_value_f is not None and np.isfinite(fill_value_f):
        valid_mask &= ~np.isclose(values_2d, fill_value_f)

    try:
        missing_value_f = (
            float(missing_value)
            if missing_value is not None
            else None
        )
    except (TypeError, ValueError):
        missing_value_f = None
    if missing_value_f is not None and np.isfinite(missing_value_f):
        valid_mask &= ~np.isclose(values_2d, missing_value_f)

    if not np.any(valid_mask):
        return np.full(
            (target_lat_1d.size, target_lon_1d.size),
            fill_value,
            dtype=np.float32,
        )

    points = np.column_stack(
        (gate_lon_2d[valid_mask], gate_lat_2d[valid_mask])
    )
    source_values = values_2d[valid_mask]
    target_lon_2d, target_lat_2d = np.meshgrid(
        target_lon_1d,
        target_lat_1d,
    )
    remapped = griddata(
        points=points,
        values=source_values,
        xi=(target_lon_2d, target_lat_2d),
        method=method,
        fill_value=fill_value,
    )
    return np.asarray(remapped, dtype=np.float32)


def build_latlon_griddata_from_template(
    template: xr.DataArray,
    data_2d: np.ndarray,
    target_lon,
    target_lat,
    data_name: str | None = None,
) -> xr.DataArray:
    """基于模板非空间维信息重建规则经纬网格。"""
    # 不做 ±1000 截断：模板可能含速度缺测填充值（如 -9999）。
    normalized = meb.checkout_griddata(
        template,
        is_single=False,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    lon_axis = np.asarray(target_lon, dtype=np.float64)
    lat_axis = np.asarray(target_lat, dtype=np.float64)
    values_2d = np.asarray(data_2d, dtype=np.float32)

    expected_shape = (lat_axis.size, lon_axis.size)
    if values_2d.shape != expected_shape:
        raise ValueError(
            f"data_2d shape must be {expected_shape}, "
            f"got {values_2d.shape}"
        )

    coords = {
        "member": normalized.member.values,
        "level": normalized.level.values,
        "time": normalized.time.values,
        "dtime": normalized.dtime.values,
        "lat": lat_axis,
        "lon": lon_axis,
    }
    expanded = values_2d.reshape(
        1,
        1,
        1,
        1,
        lat_axis.size,
        lon_axis.size,
    )
    return xr.DataArray(
        expanded,
        coords=coords,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=normalized.name if data_name is None else data_name,
        attrs=dict(normalized.attrs),
    )


def infer_target_lonlat_grid(
    gate_lon,
    gate_lat,
    target_lon=None,
    target_lat=None,
    geo_resolution_deg: float | None = 0.01,
    geo_nlon: int | None = None,
    geo_nlat: int | None = None,
    default_nlon: int | None = None,
    default_nlat: int | None = None,
):
    """根据门点经纬度范围推导规则经纬网格。"""
    if target_lon is not None and target_lat is not None:
        lon_axis = np.asarray(target_lon, dtype=np.float64)
        lat_axis = np.asarray(target_lat, dtype=np.float64)
        if lon_axis.ndim != 1 or lat_axis.ndim != 1:
            raise ValueError(
                "target_lon and target_lat must be 1D sequences"
            )
        return lon_axis, lat_axis

    gate_lon_2d = np.asarray(gate_lon, dtype=np.float64)
    gate_lat_2d = np.asarray(gate_lat, dtype=np.float64)
    valid_mask = np.isfinite(gate_lon_2d) & np.isfinite(gate_lat_2d)
    if not np.any(valid_mask):
        raise ValueError(
            "gate_lon and gate_lat do not contain any finite points"
        )

    lon_min = float(np.nanmin(gate_lon_2d[valid_mask]))
    lon_max = float(np.nanmax(gate_lon_2d[valid_mask]))
    lat_min = float(np.nanmin(gate_lat_2d[valid_mask]))
    lat_max = float(np.nanmax(gate_lat_2d[valid_mask]))

    if geo_resolution_deg is not None:
        resolution = float(geo_resolution_deg)
        if resolution <= 0.0:
            raise ValueError("geo_resolution_deg must be positive")
        nlon = max(
            int(np.ceil((lon_max - lon_min) / resolution)) + 1,
            2,
        )
        nlat = max(
            int(np.ceil((lat_max - lat_min) / resolution)) + 1,
            2,
        )
    else:
        nlon = int(
            geo_nlon if geo_nlon is not None else (default_nlon or 2)
        )
        nlat = int(
            geo_nlat if geo_nlat is not None else (default_nlat or 2)
        )
        if nlon < 2 or nlat < 2:
            raise ValueError(
                "geo_nlon and geo_nlat must be at least 2"
            )

    lon_axis = np.linspace(lon_min, lon_max, nlon, dtype=np.float64)
    lat_axis = np.linspace(lat_min, lat_max, nlat, dtype=np.float64)
    return lon_axis, lat_axis
