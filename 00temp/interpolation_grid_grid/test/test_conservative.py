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
from cli.interpolation_grid_grid_cli import _normalize_method, process


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


def test_resolve_method_conservative():
    assert _normalize_method("conservative") == "conservative"
    with pytest.raises(ValueError, match="method"):
        _normalize_method("area_weighted")
    with pytest.raises(ValueError, match="method"):
        _normalize_method("interp_gg_conservative")


def test_mdtol_out_of_range():
    with pytest.raises(ValueError, match="mdtol"):
        InterpGgConservative(mdtol=1.5)
    with pytest.raises(ValueError, match="mdtol"):
        process(
            method="conservative",
            grid=r"D:\grid.nc",
            domain="20,50,70,140,0.25,0.25",
            mdtol=2.0,
        )


def _spherical_cell_areas(lats: np.ndarray, lons: np.ndarray, dlat: float, dlon: float) -> np.ndarray:
    """``Δlon × Δsin(lat)`` 面积因子（与 area_weighted 球面约定一致）。"""
    lon_b = contiguous_bounds_1d(lons, dlon)
    lat_b = contiguous_bounds_1d(lats, dlat)
    deg2rad = np.pi / 180.0
    return np.abs(np.diff(np.sin(lat_b * deg2rad)))[:, None] * np.abs(
        np.diff(lon_b) * deg2rad
    )[None, :]


def test_mass_conservation_exact_nested():
    """源/目标域完全嵌套时，Σ(value·area) 应近似守恒。"""
    lons = np.arange(70.25, 90.0, 0.5)
    lats = np.arange(20.25, 40.0, 0.5)
    yy, xx = np.meshgrid(np.arange(lats.size), np.arange(lons.size), indexing="ij")
    data = (3.0 + 0.2 * xx + 0.1 * yy).astype(np.float32)
    grd = make_meb6d(data, lats=lats, lons=lons)
    target = meb.basicdata.grid([70.5, 89.5, 1.0], [20.5, 39.5, 1.0])
    out = InterpGgConservative(outer_value=0.0).process(grd, target)
    arr = to_compare_array(out)
    tlons = np.arange(target.nlon) * target.dlon + target.slon
    tlats = np.arange(target.nlat) * target.dlat + target.slat
    a_src = _spherical_cell_areas(lats, lons, 0.5, 0.5)
    a_tgt = _spherical_cell_areas(tlats, tlons, 1.0, 1.0)
    mass_src = float((data * a_src).sum())
    mass_tgt = float((arr * a_tgt).sum())
    assert abs(mass_src - mass_tgt) / mass_src < 1e-6

    # 常场：质量守恒且结果仍为常数
    grd_c = make_meb6d(np.full_like(data, 7.0), lats=lats, lons=lons)
    out_c = InterpGgConservative(outer_value=0.0).process(grd_c, target)
    arr_c = to_compare_array(out_c)
    mass_c_src = float((7.0 * a_src).sum())
    mass_c_tgt = float((arr_c * a_tgt).sum())
    assert abs(mass_c_src - mass_c_tgt) / mass_c_src < 1e-12
    np.testing.assert_allclose(arr_c, 7.0, atol=1e-5)


def test_low_to_high_smoke_constant_and_parent():
    """低→高非主场景：冒烟——常场仍为常数；嵌套时细格接近父格值。

    目标中心须落在源中心范围内（插件越界判定按中心，与 Linear 一致），
    否则边缘会被 ``outer_value`` 填充。
    """
    # 粗源：1°，中心 70.5..79.5 / 20.5..29.5
    lons = np.arange(70.5, 80.0, 1.0)
    lats = np.arange(20.5, 30.0, 1.0)
    data = np.empty((lats.size, lons.size), dtype=np.float32)
    for j, lat in enumerate(lats):
        for i, lon in enumerate(lons):
            data[j, i] = 100.0 + 10.0 * (lon - 70.5) + (lat - 20.5)
    grd = make_meb6d(data, lats=lats, lons=lons)

    # 细目标：0.25°，中心落在源中心范围内
    target = meb.basicdata.grid([70.625, 79.375, 0.25], [20.625, 29.375, 0.25])
    out = InterpGgConservative(outer_value=0.0).process(grd, target)
    arr = to_compare_array(out)
    assert arr.shape[0] == target.nlat and arr.shape[1] == target.nlon

    # 常场冒烟
    grd_c = make_meb6d(np.full_like(data, 6.0), lats=lats, lons=lons)
    arr_c = to_compare_array(InterpGgConservative(outer_value=0.0).process(grd_c, target))
    np.testing.assert_allclose(arr_c, 6.0, atol=1e-5)

    # 细格中心靠近某粗格中心时，应接近该父格值
    tlons = np.arange(target.nlon) * float(target.dlon) + float(target.slon)
    tlats = np.arange(target.nlat) * float(target.dlat) + float(target.slat)
    for j, lat in enumerate(tlats):
        for i, lon in enumerate(tlons):
            pi = int(np.argmin(np.abs(lons - lon)))
            pj = int(np.argmin(np.abs(lats - lat)))
            if abs(lons[pi] - lon) < 0.2 and abs(lats[pj] - lat) < 0.2:
                np.testing.assert_allclose(arr[j, i], data[pj, pi], atol=1e-4)


def test_matches_iris_area_weighted():
    """与 Iris AreaWeighted 数值对齐（无 iris 时跳过；可用 improver venv 跑）。"""
    iris = pytest.importorskip("iris")
    from iris.analysis import AreaWeighted
    from iris.coords import DimCoord
    from iris.cube import Cube

    lons = np.arange(70.25, 90.0, 0.5)
    lats = np.arange(20.25, 40.0, 0.5)
    yy, xx = np.meshgrid(np.arange(lats.size), np.arange(lons.size), indexing="ij")
    data = (3.0 + 0.2 * xx + 0.1 * yy).astype(np.float64)
    tlons = np.arange(70.5, 90.0, 1.0)
    tlats = np.arange(20.5, 40.0, 1.0)

    lon_b = contiguous_bounds_1d(lons, 0.5)
    lat_b = contiguous_bounds_1d(lats, 0.5)
    tlon_b = contiguous_bounds_1d(tlons, 1.0)
    tlat_b = contiguous_bounds_1d(tlats, 1.0)
    weights = build_area_weighted_weights(
        lon_b, lat_b, tlon_b, tlat_b, spherical=True, circular_lon=False
    )
    ours = apply_area_weighted(data, weights, tlats.size, tlons.size, mdtol=1.0)

    def _cube(arr, lat_c, lon_c):
        lat = DimCoord(
            lat_c,
            standard_name="latitude",
            units="degrees",
            coord_system=iris.coord_systems.GeogCS(6371229),
        )
        lon = DimCoord(
            lon_c,
            standard_name="longitude",
            units="degrees",
            coord_system=iris.coord_systems.GeogCS(6371229),
        )
        lat.guess_bounds()
        lon.guess_bounds()
        return Cube(arr, dim_coords_and_dims=[(lat, 0), (lon, 1)])

    src = _cube(data, lats, lons)
    tgt = _cube(np.zeros((tlats.size, tlons.size), dtype=np.float64), tlats, tlons)
    iris_out = src.regrid(tgt, AreaWeighted())
    np.testing.assert_allclose(ours, np.asarray(iris_out.data), rtol=1e-5, atol=1e-5)
