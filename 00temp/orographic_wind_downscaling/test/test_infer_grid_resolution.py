#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""infer_grid_resolution_from_coords：投影米制与真经纬推断。"""
from __future__ import annotations

import json

import numpy as np
import pytest
import xarray as xr

from orographic_wind_downscaling.src.wind_downscaling import EARTH_RADIUS_M, RoughnessCorrection


def _meter_field() -> xr.DataArray:
    """投影米制坐标（维名可为 lat/lon，units=m）。"""
    lat = np.arange(0.0, 5000.0, 1000.0, dtype=np.float64)
    lon = np.arange(0.0, 4000.0, 1000.0, dtype=np.float64)
    values = np.zeros((lat.size, lon.size), dtype=np.float32)
    return xr.DataArray(
        values,
        dims=("lat", "lon"),
        coords={
            "lat": ("lat", lat, {"units": "m"}),
            "lon": ("lon", lon, {"units": "m"}),
        },
        name="surface_altitude",
        attrs={"units": "m"},
    )


def _geo_field() -> xr.DataArray:
    """真经纬规则网格。"""
    lat = np.linspace(54.0, 55.0, 11, dtype=np.float64)
    lon = np.linspace(-5.0, -4.0, 11, dtype=np.float64)
    values = np.zeros((lat.size, lon.size), dtype=np.float32)
    return xr.DataArray(
        values,
        dims=("lat", "lon"),
        coords={
            "lat": ("lat", lat, {"units": "degrees_north"}),
            "lon": ("lon", lon, {"units": "degrees_east"}),
        },
        name="surface_altitude",
        attrs={
            "units": "m",
            "grid_mapping_attrs": json.dumps(
                {"grid_mapping_name": "latitude_longitude"},
                ensure_ascii=False,
            ),
        },
    )


def test_infer_ppres_from_projected_meter_coords() -> None:
    da = _meter_field()
    ppres = RoughnessCorrection.infer_grid_resolution_from_coords(da)
    assert ppres == pytest.approx(1000.0, abs=1e-6)


def test_infer_ppres_from_geographic_degree_coords() -> None:
    da = _geo_field()
    ppres = RoughnessCorrection.infer_grid_resolution_from_coords(da)

    dlat = float(np.median(np.abs(np.diff(da.lat.values))))
    dlon = float(np.median(np.abs(np.diff(da.lon.values))))
    lat0 = float(np.median(da.lat.values))
    dy_m = np.deg2rad(dlat) * EARTH_RADIUS_M
    dx_m = np.deg2rad(dlon) * EARTH_RADIUS_M * np.cos(np.deg2rad(lat0))
    expected = float(np.mean([abs(dy_m), abs(dx_m)]))
    assert ppres == pytest.approx(expected, rel=1e-10, abs=1e-6)
    # 1° 网格约百公里量级，绝不能把度数当米
    assert ppres > 1000.0


def test_roughness_correction_auto_ppres_geographic() -> None:
    """DataArray 真经纬地形未显式传 ppres 时，应走度→米推断。"""
    n_lat, n_lon = 5, 5
    lat = np.linspace(50.0, 50.4, n_lat)
    lon = np.linspace(0.0, 0.4, n_lon)
    field2d = np.ones((n_lat, n_lon), dtype=np.float32)
    coords = {
        "member": ["data0"],
        "level": np.array([0.0], dtype=np.float32),
        "time": np.array([np.datetime64("1970-01-01T00:00:00")]),
        "dtime": np.array([0], dtype=np.int32),
        "lat": ("lat", lat, {"units": "degrees_north"}),
        "lon": ("lon", lon, {"units": "degrees_east"}),
    }
    dims = ("member", "level", "time", "dtime", "lat", "lon")
    values = field2d[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]

    def _as_meb(name: str, units: str) -> xr.DataArray:
        return xr.DataArray(
            values.copy(),
            dims=dims,
            coords=coords,
            name=name,
            attrs={
                "units": units,
                "grid_mapping_attrs": json.dumps(
                    {"grid_mapping_name": "latitude_longitude"}
                ),
            },
        )

    pporo = _as_meb("surface_altitude", "m")
    plugin = RoughnessCorrection(
        _as_meb("a_over_s", "1"),
        _as_meb("sigma", "m"),
        pporo,
        _as_meb("modoro", "m"),
        modres=1500.0,
        z0=_as_meb("z0", "m"),
    )
    expected = RoughnessCorrection.infer_grid_resolution_from_coords(pporo)
    assert plugin.ppres == pytest.approx(expected, rel=1e-10, abs=1e-6)
    assert plugin.ppres > 1000.0
