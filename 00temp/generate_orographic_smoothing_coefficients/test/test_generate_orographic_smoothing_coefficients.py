#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""OrographicSmoothingCoefficients 单元测试与官方样例对照。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import iris
import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "improver-1.18.7"))

from generate_orographic_smoothing_coefficients.src.generate_orographic_smoothing_coefficients import (  # noqa: E402
    OrographicSmoothingCoefficients,
)
from generate_orographic_smoothing_coefficients.src.utils._gradient import (  # noqa: E402
    DEFAULT_SPHERE_RADIUS_M,
    adjacent_gradients_projected,
)

TEST_DATA_ROOT = (
    Path(__file__).resolve().parents[1]
    / "test_data"
)

_requires_official_data = pytest.mark.skipif(
    not (TEST_DATA_ROOT / "orography.nc").is_file(),
    reason="未同步 test_data（含 orography.nc）",
)


def _improver_available() -> bool:
    try:
        import improver  # noqa: F401

        return True
    except ImportError:
        return False


_requires_improver = pytest.mark.skipif(
    not _improver_available(),
    reason="未提供 improver-1.18.7（包旁路径）",
)


def _make_meb6d(
    values_2d: np.ndarray,
    *,
    lat: np.ndarray,
    lon: np.ndarray,
    name: str,
    lat_units: str | None = "m",
    lon_units: str | None = "m",
    units: str = "m",
    grid_mapping_attrs: dict | None = ...,
    coord_dtype: type = np.float32,
) -> xr.DataArray:
    """构造六维 DataArray。

    - 投影路径常用 ``coord_dtype=float32``、``units='m'|'km'``，默认可带 ``grid_mapping_attrs``；
    - 经纬度路径建议 ``coord_dtype=float64``，``units`` 为度或 ``None``，
      且 ``grid_mapping_attrs=None``（业务经纬场通常无该属性）。
    - ``units`` 为场本身单位（地形 ``m``、掩码 ``1``），勿与坐标单位混淆。
    """
    values = np.asarray(values_2d, dtype=np.float32)[
        np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
    ]
    lat_attrs = {"units": lat_units} if lat_units else {}
    lon_attrs = {"units": lon_units} if lon_units else {}
    attrs: dict = {"units": units}
    # Ellipsis：投影测试默认补 lambert；显式 None：经纬业务形态，不写该属性
    if grid_mapping_attrs is ...:
        attrs["grid_mapping_attrs"] = json.dumps(
            {"grid_mapping_name": "lambert_azimuthal_equal_area"},
            ensure_ascii=False,
        )
    elif grid_mapping_attrs is not None:
        attrs["grid_mapping_attrs"] = json.dumps(
            grid_mapping_attrs, ensure_ascii=False
        )
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": xr.DataArray(np.array([0], dtype=np.int32), dims=("member",)),
            "level": xr.DataArray(np.array([0], dtype=np.int32), dims=("level",)),
            "time": xr.DataArray(
                np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
                dims=("time",),
            ),
            "dtime": xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",)),
            "lat": xr.DataArray(
                np.asarray(lat, dtype=coord_dtype),
                dims=("lat",),
                attrs=lat_attrs,
            ),
            "lon": xr.DataArray(
                np.asarray(lon, dtype=coord_dtype),
                dims=("lon",),
                attrs=lon_attrs,
            ),
        },
        attrs=attrs,
        name=name,
    )


def _iris_cube_to_meb6d(cube) -> xr.DataArray:
    """将官方 2D Iris 地形/掩码转为 meb 六维。"""
    y_coord = cube.coord(axis="y")
    x_coord = cube.coord(axis="x")
    mapping = {}
    if cube.coord_system() is not None:
        try:
            mapping = dict(cube.coord_system().as_cartopy_crs().to_cf())
        except Exception:
            mapping = {"grid_mapping_name": "unknown"}
    return _make_meb6d(
        np.asarray(cube.data, dtype=np.float32),
        lat=y_coord.points,
        lon=x_coord.points,
        name=cube.name() or "field",
        lat_units=str(y_coord.units),
        lon_units=str(x_coord.units),
        units=str(cube.units),
        grid_mapping_attrs=mapping if mapping else ...,
    )


def test_adjacent_gradients_projected_shapes_and_values():
    """投影梯度形状正确，并等于差分/格距。"""
    values = np.array([[1.0, 2.0, 4.0], [2.0, 3.0, 5.0]], dtype=np.float32)
    lat = np.array([0.0, 2000.0], dtype=np.float32)
    lon = np.array([0.0, 2000.0, 4000.0], dtype=np.float32)
    grad_x, grad_y, lon_mid, lat_mid = adjacent_gradients_projected(
        values, lat, lon, lat_units="m", lon_units="m"
    )
    assert grad_x.shape == (2, 2)
    assert grad_y.shape == (1, 3)
    np.testing.assert_allclose(grad_x, np.diff(values, axis=1) / 2000.0)
    np.testing.assert_allclose(grad_y, np.diff(values, axis=0) / 2000.0)
    np.testing.assert_allclose(lon_mid, [1000.0, 3000.0])
    np.testing.assert_allclose(lat_mid, [1000.0])


def test_adjacent_gradients_projected_km_units_match_meters():
    """投影路径：km 坐标先换算为米算梯度；中点仍保持 km。"""
    values = np.array([[1.0, 2.0, 4.0], [2.0, 3.0, 5.0]], dtype=np.float32)
    lat_m = np.array([0.0, 2000.0], dtype=np.float64)
    lon_m = np.array([0.0, 2000.0, 4000.0], dtype=np.float64)
    gx_m, gy_m, _, _ = adjacent_gradients_projected(
        values, lat_m, lon_m, lat_units="m", lon_units="m"
    )
    lat_km = lat_m / 1000.0
    lon_km = lon_m / 1000.0
    gx_km, gy_km, lon_mid_km, lat_mid_km = adjacent_gradients_projected(
        values,
        lat_km,
        lon_km,
        lat_units="km",
        lon_units="km",
    )
    np.testing.assert_allclose(gx_km, gx_m, atol=1e-6, rtol=1e-6)
    np.testing.assert_allclose(gy_km, gy_m, atol=1e-6, rtol=1e-6)
    np.testing.assert_allclose(lon_mid_km, 0.5 * (lon_km[1:] + lon_km[:-1]))
    np.testing.assert_allclose(lat_mid_km, 0.5 * (lat_km[1:] + lat_km[:-1]))


def test_process_projected_km_units_match_meters():
    """process：km 输入与米制输入得到相同系数，中点坐标单位保持 km。"""
    values = np.arange(12, dtype=np.float32).reshape(3, 4)
    lat_m = np.array([0.0, 1000.0, 2000.0], dtype=np.float64)
    lon_m = np.array([0.0, 1000.0, 2000.0, 3000.0], dtype=np.float64)
    orog_m = _make_meb6d(values, lat=lat_m, lon=lon_m, name="orography", lat_units="m", lon_units="m")
    orog_km = _make_meb6d(
        values,
        lat=lat_m / 1000.0,
        lon=lon_m / 1000.0,
        name="orography",
        lat_units="km",
        lon_units="km",
        coord_dtype=np.float64,
    )
    cx_m, cy_m = OrographicSmoothingCoefficients(0.5, 0.0, 1.0).process(orog_m)
    cx_km, cy_km = OrographicSmoothingCoefficients(0.5, 0.0, 1.0).process(orog_km)
    np.testing.assert_allclose(cx_km.values, cx_m.values, atol=1e-6, rtol=1e-6)
    np.testing.assert_allclose(cy_km.values, cy_m.values, atol=1e-6, rtol=1e-6)
    assert cx_km.coords["lon"].attrs.get("units") == "km"
    assert cy_km.coords["lat"].attrs.get("units") == "km"
    np.testing.assert_allclose(
        cx_km.coords["lon"].values, 0.5 * (lon_m[1:] + lon_m[:-1]) / 1000.0
    )


def test_adjacent_gradients_projected_rejects_nonuniform_spacing():
    """投影路径要求等间距。"""
    values = np.ones((2, 3), dtype=np.float32)
    lat = np.array([0.0, 2000.0], dtype=np.float32)
    lon = np.array([0.0, 1000.0, 4000.0], dtype=np.float32)
    with pytest.raises(ValueError, match="非等间距"):
        adjacent_gradients_projected(
            values, lat, lon, lat_units="m", lon_units="m"
        )


@_requires_improver
def test_adjacent_gradients_latlon_matches_improver_per_interval():
    """经纬度路径：逐段 diff 格距与原 GradientBetweenAdjacentGridSquares 一致。"""
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube
    from improver.utilities.spatial import GradientBetweenAdjacentGridSquares

    radius = DEFAULT_SPHERE_RADIUS_M
    lats = np.array([30.0, 30.1, 30.2], dtype=np.float64)
    # 非等间距经度，验证不用平均格距
    lons = np.array([120.0, 120.1, 120.25, 120.5], dtype=np.float64)
    values = np.arange(12, dtype=np.float64).reshape(3, 4)

    y = DimCoord(
        lats, standard_name="latitude", units="degrees", coord_system=GeogCS(radius)
    )
    x = DimCoord(
        lons, standard_name="longitude", units="degrees", coord_system=GeogCS(radius)
    )
    cube = Cube(
        values.astype(np.float32),
        long_name="orography",
        units="m",
        dim_coords_and_dims=[(y, 0), (x, 1)],
    )
    orig_x, orig_y = GradientBetweenAdjacentGridSquares(regrid=False)(cube)

    our_x, our_y, lon_mid, lat_mid = adjacent_gradients_projected(
        values,
        lats,
        lons,
        lat_units="degrees",
        lon_units="degrees",
        sphere_radius=radius,
    )
    np.testing.assert_allclose(our_x, orig_x.data, atol=1e-10, rtol=1e-6)
    np.testing.assert_allclose(our_y, orig_y.data, atol=1e-10, rtol=1e-6)
    np.testing.assert_allclose(lon_mid, 0.5 * (lons[1:] + lons[:-1]))
    np.testing.assert_allclose(lat_mid, 0.5 * (lats[1:] + lats[:-1]))


@_requires_improver
def test_adjacent_gradients_latlon_none_units_and_decreasing_coords():
    """无 units 视为经纬；坐标递减时梯度符号与原算法一致。"""
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube
    from improver.utilities.spatial import GradientBetweenAdjacentGridSquares

    radius = DEFAULT_SPHERE_RADIUS_M
    lats = np.array([30.2, 30.1, 30.0], dtype=np.float64)
    lons = np.array([120.3, 120.2, 120.1], dtype=np.float64)
    values = np.array([[1.0, 2.0, 4.0], [2.0, 3.0, 5.0], [3.0, 4.0, 6.0]], dtype=np.float64)

    y = DimCoord(
        lats, standard_name="latitude", units="degrees", coord_system=GeogCS(radius)
    )
    x = DimCoord(
        lons, standard_name="longitude", units="degrees", coord_system=GeogCS(radius)
    )
    cube = Cube(
        values.astype(np.float32),
        long_name="orography",
        units="m",
        dim_coords_and_dims=[(y, 0), (x, 1)],
    )
    orig_x, orig_y = GradientBetweenAdjacentGridSquares(regrid=False)(cube)

    # units=None：业务经纬网格常见形态
    our_x, our_y, _, _ = adjacent_gradients_projected(
        values,
        lats,
        lons,
        lat_units=None,
        lon_units=None,
        sphere_radius=radius,
    )
    np.testing.assert_allclose(our_x, orig_x.data, atol=1e-10, rtol=1e-6)
    np.testing.assert_allclose(our_y, orig_y.data, atol=1e-10, rtol=1e-6)


@_requires_improver
def test_process_latlon_coefficients_match_original():
    """经纬度六维输入：最终平滑系数与原插件一致。"""
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube
    from improver.generate_ancillaries.generate_orographic_smoothing_coefficients import (
        OrographicSmoothingCoefficients as OrigPlugin,
    )

    radius = DEFAULT_SPHERE_RADIUS_M
    lats = np.linspace(20.0, 40.0, 11)
    lons = np.linspace(100.0, 120.0, 13)
    yy, xx = np.meshgrid(lats, lons, indexing="ij")
    values = ((xx - 110.0) ** 2) * 5.0 + ((yy - 30.0) ** 2) * 8.0

    y = DimCoord(
        lats, standard_name="latitude", units="degrees", coord_system=GeogCS(radius)
    )
    x = DimCoord(
        lons, standard_name="longitude", units="degrees", coord_system=GeogCS(radius)
    )
    cube = Cube(
        values.astype(np.float32),
        long_name="surface_altitude",
        units="m",
        dim_coords_and_dims=[(y, 0), (x, 1)],
    )
    orig = OrigPlugin(0.5, 0.0, 1.0)(cube)
    orig_x = orig.extract_cube("smoothing_coefficient_x").data
    orig_y = orig.extract_cube("smoothing_coefficient_y").data

    orog = _make_meb6d(
        values.astype(np.float32),
        lat=lats,
        lon=lons,
        name="orography",
        lat_units="degrees",
        lon_units="degrees",
        grid_mapping_attrs=None,
        coord_dtype=np.float64,
    )
    cur_x, cur_y = OrographicSmoothingCoefficients(0.5, 0.0, 1.0).process(orog)
    np.testing.assert_allclose(
        cur_x.squeeze(drop=True).values, orig_x, atol=1e-5, rtol=1e-5
    )
    np.testing.assert_allclose(
        cur_y.squeeze(drop=True).values, orig_y, atol=1e-5, rtol=1e-5
    )
    assert cur_x.coords["lon"].attrs.get("units") == "degrees"
    assert cur_y.coords["lat"].attrs.get("units") == "degrees"


@_requires_improver
def test_process_latlon_none_units_match_original():
    """经纬业务约定：坐标无 units 时走球面路径，系数与原插件一致。"""
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube
    from improver.generate_ancillaries.generate_orographic_smoothing_coefficients import (
        OrographicSmoothingCoefficients as OrigPlugin,
    )

    radius = DEFAULT_SPHERE_RADIUS_M
    lats = np.linspace(25.0, 35.0, 6)
    lons = np.linspace(110.0, 120.0, 7)
    yy, xx = np.meshgrid(lats, lons, indexing="ij")
    values = (xx - 115.0) ** 2 + (yy - 30.0) ** 2

    y = DimCoord(
        lats, standard_name="latitude", units="degrees", coord_system=GeogCS(radius)
    )
    x = DimCoord(
        lons, standard_name="longitude", units="degrees", coord_system=GeogCS(radius)
    )
    cube = Cube(
        values.astype(np.float32),
        long_name="surface_altitude",
        units="m",
        dim_coords_and_dims=[(y, 0), (x, 1)],
    )
    orig = OrigPlugin(0.5, 0.0, 1.0)(cube)
    orig_x = orig.extract_cube("smoothing_coefficient_x").data
    orig_y = orig.extract_cube("smoothing_coefficient_y").data

    orog = _make_meb6d(
        values.astype(np.float32),
        lat=lats,
        lon=lons,
        name="orography",
        lat_units=None,
        lon_units=None,
        grid_mapping_attrs=None,
        coord_dtype=np.float64,
    )
    # 确认业务经纬形态：坐标无 units、场无 grid_mapping_attrs
    assert "units" not in orog.coords["lat"].attrs
    assert "units" not in orog.coords["lon"].attrs
    assert "grid_mapping_attrs" not in orog.attrs

    cur_x, cur_y = OrographicSmoothingCoefficients(0.5, 0.0, 1.0).process(orog)
    np.testing.assert_allclose(
        cur_x.squeeze(drop=True).values, orig_x, atol=1e-5, rtol=1e-5
    )
    np.testing.assert_allclose(
        cur_y.squeeze(drop=True).values, orig_y, atol=1e-5, rtol=1e-5
    )
    # 无 units 输入时，输出中点坐标也不补 units
    assert "units" not in cur_x.coords["lon"].attrs
    assert "units" not in cur_y.coords["lat"].attrs
    assert "units" not in cur_x.coords["lat"].attrs
    assert "units" not in cur_y.coords["lon"].attrs


def test_process_rejects_invalid_coefficient_limits():
    """系数上下限超界时报错。"""
    with pytest.raises(ValueError, match="0 <= value <=0.5"):
        OrographicSmoothingCoefficients(min_gradient_smoothing_coefficient=0.6)


def test_process_basic_synthetic_field():
    """合成投影网格可生成 x/y 系数。"""
    lat = np.array([0.0, 1000.0, 2000.0], dtype=np.float32)
    lon = np.array([0.0, 1000.0, 2000.0, 3000.0], dtype=np.float32)
    values = np.arange(12, dtype=np.float32).reshape(3, 4)
    orog = _make_meb6d(values, lat=lat, lon=lon, name="orography")

    coeff_x, coeff_y = OrographicSmoothingCoefficients(0.5, 0.0, 1.0).process(orog)

    assert coeff_x.name == "smoothing_coefficient_x"
    assert coeff_y.name == "smoothing_coefficient_y"
    assert coeff_x.sizes["lat"] == 3 and coeff_x.sizes["lon"] == 3
    assert coeff_y.sizes["lat"] == 2 and coeff_y.sizes["lon"] == 4
    assert coeff_x.attrs["units"] == "1"
    assert coeff_x.attrs["power"] == 1.0
    assert np.all(coeff_x.values >= 0.0) and np.all(coeff_x.values <= 0.5)


def test_process_mask_boundary_zeros_edges():
    """use_mask_boundary=True 时仅边界系数置零。"""
    lat = np.linspace(0, 4000, 5).astype(np.float32)
    lon = np.linspace(0, 4000, 5).astype(np.float32)
    values = np.linspace(1, 25, 25, dtype=np.float32).reshape(5, 5)
    mask = np.zeros((5, 5), dtype=np.float32)
    mask[:, 2:] = 1.0
    orog = _make_meb6d(values, lat=lat, lon=lon, name="orography")
    mask_da = _make_meb6d(mask, lat=lat, lon=lon, name="land_binary_mask")

    coeff_x, _ = OrographicSmoothingCoefficients(
        0.5, 0.0, 1.0, use_mask_boundary=True
    ).process(orog, mask=mask_da)

    # x 方向边界位于 lon 索引 1-2 之间 -> 中点索引 1
    assert np.all(coeff_x.squeeze(drop=True).values[:, 1] == 0.0)


@pytest.mark.parametrize(
    ("subdir", "kwargs"),
    [
        ("basic", {"min_gradient_smoothing_coefficient": 0.5, "max_gradient_smoothing_coefficient": 0.0}),
        (
            "basic",
            {
                "min_gradient_smoothing_coefficient": 0.25,
                "max_gradient_smoothing_coefficient": 0.0,
                "kgo_name": "kgo_different_limits.nc",
            },
        ),
        (
            "basic",
            {
                "power": 0.5,
                "kgo_name": "kgo_different_power.nc",
            },
        ),
        (
            "mask_boundary",
            {
                "min_gradient_smoothing_coefficient": 0.5,
                "max_gradient_smoothing_coefficient": 0.0,
                "use_mask_boundary": True,
                "use_mask": True,
            },
        ),
        (
            "mask_zeroed",
            {
                "min_gradient_smoothing_coefficient": 0.5,
                "max_gradient_smoothing_coefficient": 0.0,
                "use_mask": True,
            },
        ),
        (
            "inverse_mask_zeroed",
            {
                "min_gradient_smoothing_coefficient": 0.5,
                "max_gradient_smoothing_coefficient": 0.0,
                "invert_mask": True,
                "use_mask": True,
            },
        ),
    ],
)
@_requires_improver
@_requires_official_data
def test_official_cases_match_kgo_and_original(subdir: str, kwargs: dict):
    """官方样例：当前实现与原算法、KGO 一致。"""
    from improver.generate_ancillaries.generate_orographic_smoothing_coefficients import (
        OrographicSmoothingCoefficients as OrigPlugin,
    )

    options = dict(kwargs)
    kgo_name = options.pop("kgo_name", "kgo.nc")
    use_mask = options.pop("use_mask", False)

    orog_cube = iris.load_cube(str(TEST_DATA_ROOT / "orography.nc"))
    mask_cube = iris.load_cube(str(TEST_DATA_ROOT / "landmask.nc")) if use_mask else None
    kgo_cubes = iris.load(str(TEST_DATA_ROOT / subdir / kgo_name))
    kgo_x = kgo_cubes.extract_cube("smoothing_coefficient_x")
    kgo_y = kgo_cubes.extract_cube("smoothing_coefficient_y")

    orog = _iris_cube_to_meb6d(orog_cube)
    mask = _iris_cube_to_meb6d(mask_cube) if mask_cube is not None else None

    current_x, current_y = OrographicSmoothingCoefficients(**options).process(
        orog, mask=mask
    )
    original = OrigPlugin(**options)(orog_cube, mask_cube)
    original_x = original.extract_cube("smoothing_coefficient_x")
    original_y = original.extract_cube("smoothing_coefficient_y")

    np.testing.assert_allclose(
        current_x.squeeze(drop=True).values, original_x.data, atol=1e-5, rtol=1e-5
    )
    np.testing.assert_allclose(
        current_y.squeeze(drop=True).values, original_y.data, atol=1e-5, rtol=1e-5
    )
    np.testing.assert_allclose(
        current_x.squeeze(drop=True).values, kgo_x.data, atol=1e-5, rtol=1e-5
    )
    np.testing.assert_allclose(
        current_y.squeeze(drop=True).values, kgo_y.data, atol=1e-5, rtol=1e-5
    )
