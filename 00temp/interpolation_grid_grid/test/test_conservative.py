# -*- coding: utf-8 -*-
"""InterpGgConservative / area_weighted 单元测试。"""
from __future__ import annotations

import numpy as np
import pytest
import meteva_base as meb

from helpers import make_meb6d, to_compare_array
from interp_gg_conservative_plugin import InterpGgConservative
from utils.area_weighted import (
    apply_area_weighted,
    build_area_weighted_weights,
    contiguous_bounds_1d,
)
from utils.util_env import resolve_args, resolve_module


def _rect_src(n: int = 10, v: float = 5.0):
    lons = np.arange(70.0, 70.0 + n, 1.0)
    lats = np.arange(20.0, 20.0 + n, 1.0)
    data = np.full((n, n), v, dtype=np.float32)
    return make_meb6d(data, lats=lats, lons=lons), lats, lons


def test_contiguous_bounds_1d():
    c = np.array([1.0, 2.0, 3.0])
    b = contiguous_bounds_1d(c, spacing=1.0)
    np.testing.assert_allclose(b, [0.5, 1.5, 2.5, 3.5])


def test_identity_weights_reproduce():
    lons = np.arange(70.0, 80.0, 1.0)
    lats = np.arange(20.0, 30.0, 1.0)
    data = (np.arange(lats.size * lons.size, dtype=np.float32).reshape(lats.size, lons.size))
    lon_b = contiguous_bounds_1d(lons, 1.0)
    lat_b = contiguous_bounds_1d(lats, 1.0)
    w = build_area_weighted_weights(lon_b, lat_b, lon_b, lat_b, spherical=True)
    out = apply_area_weighted(data, w, lats.size, lons.size, mdtol=1.0)
    np.testing.assert_allclose(out, data, atol=1e-5)


def test_constant_field_coarse_inside():
    grd, _, _ = _rect_src(10, 5.0)
    target = meb.basicdata.grid([71, 77, 2.0], [21, 27, 2.0])
    out = InterpGgConservative(outer_value=0.0).process(grd, target)
    arr = to_compare_array(out)
    assert arr.shape == (4, 4)
    np.testing.assert_allclose(arr, 5.0, atol=1e-5)


def test_outer_expand_fill():
    grd, _, _ = _rect_src(10, 5.0)
    target = meb.basicdata.grid([68, 82, 2.0], [18, 32, 2.0])
    out = InterpGgConservative(outer_value=-1.0).process(grd, target)
    arr = to_compare_array(out)
    assert -1.0 in arr
    assert 5.0 in arr


def test_outer_without_fill_returns_none():
    grd, _, _ = _rect_src(10, 5.0)
    target = meb.basicdata.grid([68, 82, 2.0], [18, 32, 2.0])
    assert InterpGgConservative(outer_value=None).process(grd, target) is None


def test_nan_source_mdtol():
    grd, lats, lons = _rect_src(8, 3.0)
    vals = np.array(grd.values, copy=True)
    vals[..., 0, 0] = np.nan
    grd = grd.copy(data=vals)
    target = meb.basicdata.grid([70, 76, 2.0], [20, 26, 2.0])
    # mdtol=1：只要有有效贡献即可
    out1 = InterpGgConservative(outer_value=-999.0, mdtol=1.0).process(grd, target)
    assert np.isfinite(to_compare_array(out1)).any()
    # mdtol=0：几乎不容忍缺测，角落目标更易被填
    out0 = InterpGgConservative(outer_value=-999.0, mdtol=0.0).process(grd, target)
    filled = to_compare_array(out0) == -999.0
    assert filled.any()


def test_resolve_module_conservative():
    assert resolve_module("conservative") == "conservative"
    assert resolve_module("area_weighted") == "conservative"
    assert resolve_module("interp_gg_conservative") == "conservative"
    got = resolve_args(
        module="conservative",
        grid=r"D:\grid.nc",
        domain="20,50,70,140,0.25,0.25",
    )
    assert got["module"] == "conservative"
    assert got["mdtol"] == 1.0
    assert got["outer_value"] == 0.0


def test_resolve_mdtol_override():
    got = resolve_args(
        module="conservative",
        grid=r"D:\grid.nc",
        domain="20,50,70,140,0.25,0.25",
        mdtol=0.5,
    )
    assert got["mdtol"] == 0.5


def test_mdtol_out_of_range():
    with pytest.raises(ValueError, match="mdtol"):
        InterpGgConservative(mdtol=1.5)
    with pytest.raises(ValueError, match="mdtol"):
        resolve_args(
            module="conservative",
            grid=r"D:\grid.nc",
            domain="20,50,70,140,0.25,0.25",
            mdtol=2.0,
        )
