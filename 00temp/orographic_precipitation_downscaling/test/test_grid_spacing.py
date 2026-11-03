#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""地形增强：投影米制与真经纬格距推断。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orographic_precipitation_downscaling.src.utils._grid import (
    EARTH_RADIUS_M,
    _estimate_grid_spacing_meters,
    _get_data_crs,
    _grid_spacings_meters,
    _is_geographic_spatial,
)


def _meter_field() -> xr.DataArray:
    """投影米制坐标（维名 lat/lon，units=m）。"""
    lat = np.arange(0.0, 5000.0, 1000.0, dtype=np.float64)
    lon = np.arange(0.0, 4000.0, 1000.0, dtype=np.float64)
    return xr.DataArray(
        np.zeros((lat.size, lon.size), dtype=np.float32),
        dims=("lat", "lon"),
        coords={
            "lat": ("lat", lat, {"units": "m"}),
            "lon": ("lon", lon, {"units": "m"}),
        },
        attrs={"units": "m"},
    )


def _geo_field(*, with_units: bool = True, with_mapping: bool = False) -> xr.DataArray:
    """真经纬规则网格。"""
    lat = np.linspace(40.0, 50.0, 11, dtype=np.float64)
    lon = np.linspace(-10.0, 0.0, 11, dtype=np.float64)
    lat_attrs = {"units": "degrees_north"} if with_units else {}
    lon_attrs = {"units": "degrees_east"} if with_units else {}
    attrs: dict = {"units": "m"}
    if with_mapping:
        attrs["grid_mapping_attrs"] = json.dumps(
            {"grid_mapping_name": "latitude_longitude"},
            ensure_ascii=False,
        )
    return xr.DataArray(
        np.zeros((lat.size, lon.size), dtype=np.float32),
        dims=("lat", "lon"),
        coords={
            "lat": ("lat", lat, lat_attrs),
            "lon": ("lon", lon, lon_attrs),
        },
        attrs=attrs,
    )


def _expected_geo_spacings(da: xr.DataArray) -> tuple[float, float]:
    dlat = float(np.mean(np.abs(np.diff(da.lat.values))))
    dlon = float(np.mean(np.abs(np.diff(da.lon.values))))
    lat0 = float(np.mean(da.lat.values))
    dy_m = np.deg2rad(dlat) * EARTH_RADIUS_M
    dx_m = np.deg2rad(dlon) * EARTH_RADIUS_M * np.cos(np.deg2rad(lat0))
    return abs(dy_m), abs(dx_m)


def test_projected_meter_coords_keep_metre_spacing() -> None:
    da = _meter_field()
    assert not _is_geographic_spatial(da)
    dy, dx = _grid_spacings_meters(da)
    assert dy == pytest.approx(1000.0, abs=1e-6)
    assert dx == pytest.approx(1000.0, abs=1e-6)


def test_geographic_degree_units_convert_to_metres() -> None:
    da = _geo_field(with_units=True)
    assert _is_geographic_spatial(da)
    assert _get_data_crs(da).is_geographic
    dy, dx = _grid_spacings_meters(da)
    exp_dy, exp_dx = _expected_geo_spacings(da)
    assert dy == pytest.approx(exp_dy, rel=1e-10)
    assert dx == pytest.approx(exp_dx, rel=1e-10)
    assert _estimate_grid_spacing_meters(da) > 1000.0


def test_geographic_without_units_matches_degree_units() -> None:
    """业务 meb 常不写坐标 units，应与显式度单位走同一经纬换算。"""
    with_units = _geo_field(with_units=True)
    no_units = _geo_field(with_units=False)
    assert _is_geographic_spatial(no_units)
    assert _get_data_crs(no_units).is_geographic
    dy_u, dx_u = _grid_spacings_meters(with_units)
    dy_n, dx_n = _grid_spacings_meters(no_units)
    assert dy_n == pytest.approx(dy_u, rel=1e-10)
    assert dx_n == pytest.approx(dx_u, rel=1e-10)
    # 1° 量级格距约数十至百公里，绝不能落到默认 1 km
    assert dy_n > 1000.0
    assert dx_n > 1000.0


def test_geographic_mapping_without_units() -> None:
    da = _geo_field(with_units=False, with_mapping=True)
    assert _is_geographic_spatial(da)
    dy, dx = _grid_spacings_meters(da)
    exp_dy, exp_dx = _expected_geo_spacings(da)
    assert dy == pytest.approx(exp_dy, rel=1e-10)
    assert dx == pytest.approx(exp_dx, rel=1e-10)


def test_renamed_projected_coords_without_units_stay_metres() -> None:
    """投影维仅改名为 lat/lon、数值仍为米、无 units 时，不可当经纬。"""
    lat = np.arange(0.0, 20000.0, 2000.0, dtype=np.float64)
    lon = np.arange(0.0, 10000.0, 2000.0, dtype=np.float64)
    da = xr.DataArray(
        np.zeros((lat.size, lon.size), dtype=np.float32),
        dims=("lat", "lon"),
        coords={"lat": lat, "lon": lon},
        attrs={"units": "m"},
    )
    assert not _is_geographic_spatial(da)
    dy, dx = _grid_spacings_meters(da)
    assert dy == pytest.approx(2000.0, abs=1e-6)
    assert dx == pytest.approx(2000.0, abs=1e-6)


def test_numpy_keeps_default_kilometre_spacing() -> None:
    arr = np.zeros((4, 5), dtype=np.float32)
    assert _grid_spacings_meters(arr) == (1000.0, 1000.0)
    assert _estimate_grid_spacing_meters(arr) == 1000.0
