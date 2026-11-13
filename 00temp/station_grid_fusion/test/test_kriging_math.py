# -*- coding: utf-8 -*-
"""克里金类内局部求解的纯数值测试（不依赖业务样例文件）。"""
from __future__ import annotations

import numpy as np
import pytest

from interp_sg_kriging import InterpSgKriging


def test_variogram_spherical_limits() -> None:
    sill, rng, nugget = 4.0, 10.0, 0.5
    assert float(InterpSgKriging._variogram(0.0, "spherical", sill, rng, nugget)) == pytest.approx(
        nugget
    )
    assert float(InterpSgKriging._variogram(rng, "spherical", sill, rng, nugget)) == pytest.approx(
        sill
    )
    assert float(
        InterpSgKriging._variogram(2 * rng, "spherical", sill, rng, nugget)
    ) == pytest.approx(sill)


def test_krige_point_recovers_constant_field() -> None:
    plugin = InterpSgKriging(model="spherical", sill=1.0, range_=2.0, nugget=0.0)
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    values = np.full(4, 7.5)
    target = np.array([0.5, 0.5, 0.0], dtype=np.float64)
    est = plugin._krige_point(xyz, values, target, sill=1.0, range_=2.0)
    assert est == pytest.approx(7.5, abs=1e-6)


def test_krige_point_single_neighbor() -> None:
    plugin = InterpSgKriging(model="spherical", sill=1.0, range_=2.0)
    xyz = np.array([[0.0, 0.0, 0.0]], dtype=np.float64)
    values = np.array([3.0], dtype=np.float64)
    target = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    est = plugin._krige_point(xyz, values, target, sill=1.0, range_=2.0)
    assert est == pytest.approx(3.0)


def test_krige_grid_shape() -> None:
    plugin = InterpSgKriging(model="spherical", sill=1.0, range_=2.0, nearNum=3)
    xyz_sta = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)
    values = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    xyz_grid = np.array([[0.25, 0.25, 0.0], [0.75, 0.25, 0.0]], dtype=np.float64)
    out = plugin._krige_grid(xyz_sta, values, xyz_grid)
    assert out.shape == (2,)
    assert np.all(np.isfinite(out))
