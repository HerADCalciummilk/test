#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""极坐标体扫转换与校验 CLI 工具测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_wind_dealiasing.cli import _write_griddata_to_nc
from radar_wind_dealiasing.cli.polar_volume_main import (
    pyart_radar_to_polar_volume,
    read_polar_volume,
    validate_polar_volume,
)


class _FakeRadar:
    """提供转换测试所需的最小 Py-ART Radar 接口。"""

    def __init__(self):
        velocity = np.ma.array(
            [
                [1.0, 2.0, 3.0, 4.0],
                [1.0, 2.0, 3.0, 4.0],
                [5.0, 6.0, 7.0, 8.0],
                [5.0, 6.0, 7.0, 8.0],
                [5.0, 6.0, 7.0, 8.0],
            ],
            mask=[
                [False, False, False, True],
                [False, False, False, False],
                [False, False, False, False],
                [False, False, False, False],
                [False, False, False, False],
            ],
            dtype=np.float32,
        )
        self.nrays = 5
        self.ngates = 4
        self.nsweeps = 2
        self.scan_type = "ppi"
        self.fields = {
            "velocity": {
                "data": velocity,
                "units": "m/s",
                "long_name": "Doppler velocity",
                "_FillValue": np.float32(-9999.0),
            }
        }
        self.sweep_start_ray_index = {"data": np.array([0, 2], dtype=np.int32)}
        self.sweep_end_ray_index = {"data": np.array([1, 4], dtype=np.int32)}
        self.fixed_angle = {"data": np.array([0.5, 1.5], dtype=np.float32)}
        self.azimuth = {
            "data": np.array([0.0, 180.0, 0.0, 120.0, 240.0]),
            "units": "degrees",
        }
        self.elevation = {
            "data": np.array([0.5, 0.5, 1.5, 1.5, 1.5]),
            "units": "degrees",
        }
        self.range = {
            "data": np.array([0.0, 1000.0, 2000.0, 3000.0]),
            "units": "meters",
        }
        self.longitude = {"data": np.array([116.0])}
        self.latitude = {"data": np.array([40.0])}
        self.altitude = {"data": np.array([50.0])}
        self.time = {
            "data": np.array([0.0]),
            "units": "seconds since 2020-01-01T00:00:00Z",
        }
        self.antenna_transition = None

    def get_nyquist_vel(self, sweep, check_uniform=False):
        del check_uniform
        return (5.0, 10.0)[sweep]


def test_pyart_radar_to_polar_volume_preserves_volume_layout():
    """转换结果应保存完整 ray/gate 数据和逐 sweep 元数据。"""
    volume = pyart_radar_to_polar_volume(_FakeRadar(), "velocity")
    info = validate_polar_volume(volume, require_geolocation=True)

    assert volume.dims == (
        "member",
        "level",
        "time",
        "dtime",
        "lat",
        "lon",
    )
    assert volume.shape == (1, 1, 1, 1, 5, 4)
    assert volume.dtype == np.float32
    assert np.isnan(volume.values[0, 0, 0, 0, 0, 3])
    assert info.nsweeps == 2
    assert "antenna_transition" not in volume.coords
    np.testing.assert_array_equal(info.sweep_start_ray_index, [0, 2])
    np.testing.assert_array_equal(info.sweep_end_ray_index, [1, 4])
    np.testing.assert_allclose(info.nyquist_velocity, [5.0, 10.0])
    np.testing.assert_allclose(volume.coords["range"], [0.0, 1000.0, 2000.0, 3000.0])


def test_pyart_radar_to_polar_volume_copies_antenna_transition():
    """Radar 提供 antenna_transition 时应写入 ray 维坐标。"""
    radar = _FakeRadar()
    radar.antenna_transition = {
        "data": np.array([0, 1, 0, 0, 1], dtype=np.int8),
        "long_name": "antenna_transition",
    }

    volume = pyart_radar_to_polar_volume(radar, "velocity")

    assert "antenna_transition" in volume.coords
    np.testing.assert_array_equal(
        volume.coords["antenna_transition"].values,
        [0, 1, 0, 0, 1],
    )


def test_validate_polar_volume_rejects_non_contiguous_sweeps():
    """sweep 边界存在间隙时应拒绝输入。"""
    volume = pyart_radar_to_polar_volume(_FakeRadar(), "velocity")
    volume.attrs["sweep_start_ray_index"] = [0, 3]

    with pytest.raises(ValueError, match="contiguous"):
        validate_polar_volume(volume)


def test_validate_polar_volume_rejects_wrong_nyquist_count():
    """Nyquist 数量与 sweep 数不一致时应拒绝输入。"""
    volume = pyart_radar_to_polar_volume(_FakeRadar(), "velocity")
    volume.attrs["nyquist_velocity"] = [5.0, 10.0, 15.0]

    with pytest.raises(ValueError, match="one value per sweep"):
        validate_polar_volume(volume)


def test_extract_polar_volume_sweep_keeps_single_layer_layout():
    """截取单个扫描层后应重置为单层边界并保留六维约定。"""
    from radar_wind_dealiasing.cli.polar_volume_main import extract_polar_volume_sweep

    volume = pyart_radar_to_polar_volume(_FakeRadar(), "velocity")
    sweep1 = extract_polar_volume_sweep(volume, sweep_index=1)
    info = validate_polar_volume(sweep1, require_geolocation=True)

    assert sweep1.shape == (1, 1, 1, 1, 3, 4)
    assert info.nsweeps == 1
    np.testing.assert_array_equal(info.sweep_start_ray_index, [0])
    np.testing.assert_array_equal(info.sweep_end_ray_index, [2])
    np.testing.assert_allclose(info.nyquist_velocity, [10.0])
    np.testing.assert_allclose(sweep1.values[0, 0, 0, 0, 0], [5.0, 6.0, 7.0, 8.0])


def test_polar_volume_netcdf_roundtrip_preserves_auxiliary_coordinates(tmp_path):
    """CLI 写入和读取后应保留体扫属性及辅助坐标。"""
    volume = pyart_radar_to_polar_volume(_FakeRadar(), "velocity")
    path = tmp_path / "velocity_volume.nc"

    _write_griddata_to_nc(volume, str(path))
    restored = read_polar_volume(path, value_name="velocity")
    info = validate_polar_volume(
        restored,
        require_geolocation=True,
    )

    assert info.nsweeps == 2
    assert "azimuth" in restored.coords
    assert "elevation" in restored.coords
    assert "range" in restored.coords
    np.testing.assert_array_equal(
        restored.attrs["sweep_start_ray_index"],
        [0, 2],
    )
