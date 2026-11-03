#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极坐标到经纬度门点坐标转换测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from radar_wind_dealiasing.src.utils._geo_remap import (
    mask_outside_radar_coverage,
    polar_to_lonlat,
    remap_gate_data_to_latlon_grid,
)


def test_polar_to_lonlat_returns_expected_shape():
    """输出门点经纬度应与 azimuth x range 门点拓扑一致。"""
    gate_lon, gate_lat = polar_to_lonlat(
        radar_lon=116.0,
        radar_lat=40.0,
        azimuth_deg=np.array([0.0, 90.0, 180.0, 270.0]),
        range_m=np.array([0.0, 1000.0, 2000.0]),
    )

    assert gate_lon.shape == (4, 3)
    assert gate_lat.shape == (4, 3)


def test_polar_to_lonlat_zero_range_stays_at_radar_site():
    """零径距门点应落在雷达站点本身。"""
    radar_lon = 116.5
    radar_lat = 39.9

    gate_lon, gate_lat = polar_to_lonlat(
        radar_lon=radar_lon,
        radar_lat=radar_lat,
        azimuth_deg=np.array([0.0, 90.0, 180.0, 270.0]),
        range_m=np.array([0.0, 1000.0]),
    )

    np.testing.assert_allclose(gate_lon[:, 0], radar_lon, atol=1e-10)
    np.testing.assert_allclose(gate_lat[:, 0], radar_lat, atol=1e-10)


def test_polar_to_lonlat_cardinal_directions_change_as_expected():
    """正北增纬、正东增经、正南减纬、正西减经。"""
    radar_lon = 116.0
    radar_lat = 40.0
    azimuth_deg = np.array([0.0, 90.0, 180.0, 270.0])
    range_m = np.array([1000.0])

    gate_lon, gate_lat = polar_to_lonlat(
        radar_lon=radar_lon,
        radar_lat=radar_lat,
        azimuth_deg=azimuth_deg,
        range_m=range_m,
    )

    north_lon, east_lon, south_lon, west_lon = gate_lon[:, 0]
    north_lat, east_lat, south_lat, west_lat = gate_lat[:, 0]

    assert north_lat > radar_lat
    assert south_lat < radar_lat
    assert east_lon > radar_lon
    assert west_lon < radar_lon

    np.testing.assert_allclose(north_lon, radar_lon, atol=1e-6)
    np.testing.assert_allclose(south_lon, radar_lon, atol=1e-6)
    np.testing.assert_allclose(east_lat, radar_lat, atol=1e-6)
    np.testing.assert_allclose(west_lat, radar_lat, atol=1e-6)


def test_remap_gate_data_to_latlon_grid_returns_target_shape():
    """插值结果形状应与目标规则经纬网格一致。"""
    values = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    gate_lon = np.array([[100.0, 101.0], [100.0, 101.0]], dtype=np.float64)
    gate_lat = np.array([[30.0, 30.0], [31.0, 31.0]], dtype=np.float64)

    remapped = remap_gate_data_to_latlon_grid(
        values=values,
        gate_lon=gate_lon,
        gate_lat=gate_lat,
        target_lon=np.array([100.0, 100.5, 101.0], dtype=np.float64),
        target_lat=np.array([30.0, 30.5, 31.0], dtype=np.float64),
        method="nearest",
    )

    assert remapped.shape == (3, 3)


def test_remap_gate_data_to_latlon_grid_nearest_preserves_exact_points():
    """最近邻插值在目标点与源门点重合时应保留原值。"""
    values = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    gate_lon = np.array([[100.0, 101.0], [100.0, 101.0]], dtype=np.float64)
    gate_lat = np.array([[30.0, 30.0], [31.0, 31.0]], dtype=np.float64)

    remapped = remap_gate_data_to_latlon_grid(
        values=values,
        gate_lon=gate_lon,
        gate_lat=gate_lat,
        target_lon=np.array([100.0, 101.0], dtype=np.float64),
        target_lat=np.array([30.0, 31.0], dtype=np.float64),
        method="nearest",
    )

    np.testing.assert_allclose(remapped, values)


def test_remap_gate_data_to_latlon_grid_ignores_fill_value_sentinels():
    """有限哨兵值不应参与插值。"""
    fill_value = -9999.0
    values = np.array([[fill_value, 2.0], [3.0, 4.0]], dtype=np.float32)
    gate_lon = np.array([[100.0, 101.0], [100.0, 101.0]], dtype=np.float64)
    gate_lat = np.array([[30.0, 30.0], [31.0, 31.0]], dtype=np.float64)

    remapped = remap_gate_data_to_latlon_grid(
        values=values,
        gate_lon=gate_lon,
        gate_lat=gate_lat,
        target_lon=np.array([100.0, 101.0], dtype=np.float64),
        target_lat=np.array([30.0, 31.0], dtype=np.float64),
        method="nearest",
        fill_value=fill_value,
    )

    assert np.isfinite(remapped[0, 0])
    assert not np.isclose(remapped[0, 0], fill_value)
    assert np.all(np.abs(remapped) < 1000.0)


def test_mask_outside_radar_coverage_masks_points_beyond_radius():
    """规则经纬网格超出雷达覆盖圆外时应被置为缺测。"""
    data_2d = np.ones((3, 3), dtype=np.float32)
    target_lon = np.array([116.0, 116.01, 116.02], dtype=np.float64)
    target_lat = np.array([40.0, 40.01, 40.02], dtype=np.float64)
    gate_lon = np.array([[116.0, 116.005], [116.0, 116.005]], dtype=np.float64)
    gate_lat = np.array([[40.0, 40.0], [40.005, 40.005]], dtype=np.float64)

    masked = mask_outside_radar_coverage(
        data_2d,
        target_lon=target_lon,
        target_lat=target_lat,
        radar_lon=116.0,
        radar_lat=40.0,
        gate_lon=gate_lon,
        gate_lat=gate_lat,
        fill_value=np.nan,
    )

    assert np.isnan(masked[-1, -1])
    assert np.isfinite(masked[0, 0])
