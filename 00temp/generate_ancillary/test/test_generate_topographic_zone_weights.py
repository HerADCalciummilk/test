#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GenerateTopographicZoneWeights 单元测试。"""

from pathlib import Path
import json
import sys

import iris
import numpy as np
import pytest
import xarray as xr

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "improver-1.18.7"))

from generate_ancillary.src.generate_ancillary import THRESHOLDS_DICT  # noqa: E402
from generate_ancillary.src.generate_topographic_zone_weights import (  # noqa: E402
    GenerateTopographicZoneWeights,
)

RESOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "generate-topography-bands-weights"
)

_requires_official_data = pytest.mark.skipif(
    not (RESOURCE_ROOT / "basic" / "input_orog.nc").is_file(),
    reason="未同步 test_data/generate-topography-bands-weights",
)
_requires_multi_data = pytest.mark.skipif(
    not (RESOURCE_ROOT / "multi_realization" / "kgo.nc").is_file(),
    reason="未同步 test_data/generate-topography-bands-weights/multi_realization",
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


def make_orography_meb6d(data: np.ndarray) -> xr.DataArray:
    """构造六维地形场。"""
    values = np.asarray(data, dtype=np.float32)[
        np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
    ]
    ny, nx = data.shape
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": ["m00"],
            "level": np.array([0], dtype=np.int32),
            "time": np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
            "dtime": np.array([0], dtype=np.int32),
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        attrs={"units": "m"},
        name="orography",
    )


def make_landmask_meb6d(data: np.ndarray) -> xr.DataArray:
    """构造六维海陆掩码。"""
    values = np.asarray(data, dtype=np.float32)[
        np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
    ]
    ny, nx = data.shape
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": ["m00"],
            "level": np.array([0], dtype=np.int32),
            "time": np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
            "dtime": np.array([0], dtype=np.int32),
            "lat": np.arange(ny, dtype=np.float32),
            "lon": np.arange(nx, dtype=np.float32),
        },
        name="land_binary_mask",
    )


class TestCalculateWeights:
    """测试带内权重插值。"""

    def setup_method(self) -> None:
        self.plugin = GenerateTopographicZoneWeights()

    def test_one_point(self) -> None:
        result = self.plugin.calculate_weights(np.array([125]), [100, 200])
        np.testing.assert_array_almost_equal(result, np.array([0.75]))

    def test_multiple_points_matching(self) -> None:
        result = self.plugin.calculate_weights(np.array([100, 150, 200]), [100, 200])
        np.testing.assert_array_almost_equal(result, np.array([0.5, 1.0, 0.5]))

    def test_multiple_points_not_matching(self) -> None:
        result = self.plugin.calculate_weights(np.array([110, 140, 190]), [100, 200])
        np.testing.assert_array_almost_equal(result, np.array([0.6, 0.9, 0.6]))

    def test_point_beyond_bands(self) -> None:
        result = self.plugin.calculate_weights(np.array([90, 150, 210]), [100, 200])
        np.testing.assert_array_almost_equal(result, np.array([0.5, 1.0, 0.5]))


class TestAdjacentBands:
    """测试相邻带权重分配。"""

    def setup_method(self) -> None:
        self.plugin = GenerateTopographicZoneWeights()

    def test_upper_equal_to_max_band(self) -> None:
        weights = np.zeros((1, 2, 2))
        orography_band = np.array([[25.0, 50.0], [75.0, 100.0]])
        result = self.plugin.add_weight_to_upper_adjacent_band(
            weights, orography_band, 50.0, 0, 0
        )
        np.testing.assert_array_almost_equal(
            result, np.array([[[0.0, 0.0], [1.0, 1.0]]])
        )

    def test_upper_not_equal_to_max_band(self) -> None:
        weights = np.array(
            [[[1.0, 1.0], [0.75, 0.5]], [[0.0, 0.0], [0.0, 0.0]]]
        )
        orography_band = np.array([[25.0, 50.0], [75.0, 100.0]])
        result = self.plugin.add_weight_to_upper_adjacent_band(
            weights, orography_band, 50.0, 0, 1
        )
        expected = np.array(
            [[[1.0, 1.0], [0.75, 0.5]], [[0.0, 0.0], [0.25, 0.5]]]
        )
        np.testing.assert_array_almost_equal(result, expected)

    def test_lower_equal_to_zeroth_band(self) -> None:
        weights = np.zeros((1, 2, 2))
        orography_band = np.array([[25.0, 50.0], [75.0, 100.0]])
        result = self.plugin.add_weight_to_lower_adjacent_band(
            weights, orography_band, 50.0, 0
        )
        np.testing.assert_array_almost_equal(
            result, np.array([[[1.0, 0.0], [0.0, 0.0]]])
        )

    def test_lower_not_equal_to_zeroth_band(self) -> None:
        weights = np.array(
            [[[0.0, 0.0], [0.0, 0.0]], [[0.75, 1.0], [1.0, 1.0]]]
        )
        orography_band = np.array([[25.0, 50.0], [75.0, 100.0]])
        result = self.plugin.add_weight_to_lower_adjacent_band(
            weights, orography_band, 50.0, 1
        )
        expected = np.array(
            [[[0.25, 0.0], [0.0, 0.0]], [[0.75, 1.0], [1.0, 1.0]]]
        )
        np.testing.assert_array_almost_equal(result, expected)


class TestProcess:
    """测试 process 端到端。"""

    def setup_method(self) -> None:
        self.plugin = GenerateTopographicZoneWeights()
        self.orography = np.array([[10.0, 25.0], [75.0, 100.0]], dtype=np.float32)
        self.landmask = np.array([[0, 1], [1, 1]], dtype=np.float32)
        self.thresholds_dict = {"bounds": [[0, 50], [50, 200]], "units": "m"}

    def test_numpy_basic_no_mask(self) -> None:
        expected = np.array(
            [[[1.0, 1.0], [0.33, 0.17]], [[0.0, 0.0], [0.67, 0.83]]],
            dtype=np.float32,
        )
        result = self.plugin.process(self.orography, self.thresholds_dict)
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_almost_equal(result, expected, decimal=2)

    def test_numpy_with_landmask(self) -> None:
        expected_data = np.array(
            [[[1e20, 1.0], [0.33, 0.17]], [[1e20, 0.0], [0.67, 0.83]]],
            dtype=np.float32,
        )
        expected_mask = np.array(
            [[[True, False], [False, False]], [[True, False], [False, False]]]
        )
        result = self.plugin.process(
            self.orography, self.thresholds_dict, self.landmask
        )
        assert np.ma.isMaskedArray(result)
        np.testing.assert_array_almost_equal(result.data, expected_data, decimal=2)
        np.testing.assert_array_equal(result.mask, expected_mask)

    def test_numpy_three_bands(self) -> None:
        orography = np.array(
            [[10.0, 40.0, 45.0], [70.0, 80.0, 95.0], [115.0, 135.0, 145.0]],
            dtype=np.float32,
        )
        landmask = np.ones_like(orography)
        thresholds = {"bounds": [[0, 50], [50, 100], [100, 150]], "units": "m"}
        expected = np.array(
            [
                [[1.0, 0.7, 0.6], [0.1, 0.0, 0.0], [0.0, 0.0, 0.0]],
                [[0.0, 0.3, 0.4], [0.9, 0.9, 0.6], [0.2, 0.0, 0.0]],
                [[0.0, 0.0, 0.0], [0.0, 0.1, 0.4], [0.8, 1.0, 1.0]],
            ]
        )
        result = self.plugin.process(orography, thresholds, landmask)
        np.testing.assert_array_almost_equal(result, expected, decimal=2)

    def test_numpy_different_band_units(self) -> None:
        thresholds = {"bounds": [[0, 0.05], [0.05, 0.2]], "units": "km"}
        expected = np.array(
            [[[1.0, 1.0], [0.33, 0.17]], [[0.0, 0.0], [0.67, 0.83]]],
            dtype=np.float32,
        )
        landmask = np.ones_like(self.orography)
        result = self.plugin.process(self.orography, thresholds, landmask)
        np.testing.assert_array_almost_equal(result, expected, decimal=2)

    def test_numpy_invalid_shape(self) -> None:
        with pytest.raises(ValueError, match="须为二维数组"):
            self.plugin.process(
                np.array([[[0.0, 25.0], [75.0, 100.0]]]),
                self.thresholds_dict,
            )

    def test_warning_orography_above_bands(self) -> None:
        orography = np.array([[60.0, 70.0], [80.0, 90.0]], dtype=np.float32)
        thresholds = {"bounds": [[0, 50]], "units": "m"}
        with pytest.warns(UserWarning, match="maximum orography"):
            self.plugin.process(orography, thresholds, np.ones_like(orography))

    def test_warning_orography_below_bands(self) -> None:
        orography = np.array([[60.0, 70.0], [80.0, 90.0]], dtype=np.float32)
        thresholds = {"bounds": [[100, 150]], "units": "m"}
        with pytest.warns(UserWarning, match="minimum orography"):
            self.plugin.process(orography, thresholds, np.ones_like(orography))

    def test_xarray_meb6d_metadata(self) -> None:
        orog = make_orography_meb6d(self.orography)
        result = self.plugin.process(orog, self.thresholds_dict)
        assert isinstance(result, xr.DataArray)
        assert result.name == "topographic_zone_weights"
        assert result.attrs["units"] == "1"
        assert result.attrs["topographic_zones_include_seapoints"] == "True"
        assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
        assert result.sizes["level"] == 2
        np.testing.assert_array_almost_equal(
            result.coords["level"].values, np.array([25.0, 125.0], dtype=np.float32)
        )
        np.testing.assert_array_almost_equal(
            result.coords["level_lower_bound"].values,
            np.array([0.0, 50.0], dtype=np.float32),
        )
        expected = np.array(
            [[[1.0, 1.0], [0.33, 0.17]], [[0.0, 0.0], [0.67, 0.83]]],
            dtype=np.float32,
        )
        np.testing.assert_array_almost_equal(
            result.values[0, :, 0, 0, :, :], expected, decimal=2
        )

    def test_xarray_with_landmask_nan_sea(self) -> None:
        orog = make_orography_meb6d(self.orography)
        land = make_landmask_meb6d(self.landmask)
        result = self.plugin.process(orog, self.thresholds_dict, land)
        assert result.attrs["topographic_zones_include_seapoints"] == "False"
        sea_vals = result.values[0, :, 0, 0, 0, 0]
        assert np.all(np.isnan(sea_vals))
        np.testing.assert_allclose(result.values[0, 0, 0, 0, 0, 1], 1.0, atol=1e-2)


def to_meb6d_grid(data: xr.DataArray) -> xr.DataArray:
    """将二维网格场包装为 meteva_base 六维格式。"""
    if data.dims[-2:] == ("projection_y_coordinate", "projection_x_coordinate"):
        data = data.rename(
            {
                "projection_y_coordinate": "lat",
                "projection_x_coordinate": "lon",
            }
        )
    elif data.dims[-2:] != ("lat", "lon"):
        data = data.rename({data.dims[-2]: "lat", data.dims[-1]: "lon"})

    expanded = data.expand_dims(
        member=np.array([0], dtype=np.int32),
        level=np.array([0], dtype=np.int32),
        time=np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
        dtime=np.array([0], dtype=np.int32),
    )
    return expanded.transpose("member", "level", "time", "dtime", "lat", "lon")


def load_primary_dataarray(path: Path) -> xr.DataArray:
    """读取 NetCDF 文件中的主变量。"""
    dataset = xr.open_dataset(path, decode_timedelta=False)
    for name, data_array in dataset.data_vars.items():
        if "bnds" not in name and name != "lambert_azimuthal_equal_area":
            return data_array
    raise ValueError(f"未在 {path} 中找到主数据变量。")


def load_thresholds_from_json(path: Path) -> dict:
    """读取 JSON 格式的地形带定义。"""
    with open(path, "r", encoding="utf-8") as infile:
        return json.load(infile)


def _values_with_nan(data) -> np.ndarray:
    """MaskedArray / 大填充值统一转为 NaN，便于与迁移版对照。"""
    if np.ma.isMaskedArray(data):
        return np.ma.filled(data, np.nan).astype(np.float64)
    arr = np.asarray(data, dtype=np.float64)
    return np.where(np.isfinite(arr) & (np.abs(arr) < 1.0e20), arr, np.nan)


def assert_matches_reference(result: xr.DataArray, expected: xr.DataArray) -> None:
    """比较迁移版结果与 KGO 的数值和地形带中心。"""
    result_core = result.squeeze(drop=True)
    if "level" in result_core.dims and "topographic_zone" not in result_core.dims:
        result_core = result_core.rename({"level": "topographic_zone"})

    np.testing.assert_allclose(
        _values_with_nan(result_core.values),
        _values_with_nan(expected.values),
        equal_nan=True,
        atol=1e-5,
        rtol=1e-5,
    )
    np.testing.assert_allclose(
        result_core.coords["topographic_zone"].values,
        expected.coords["topographic_zone"].values,
    )
    if "topographic_zone_bnds" in expected.coords:
        np.testing.assert_allclose(
            result.coords["level_lower_bound"].values,
            expected.coords["topographic_zone_bnds"].values[:, 0],
        )
        np.testing.assert_allclose(
            result.coords["level_upper_bound"].values,
            expected.coords["topographic_zone_bnds"].values[:, 1],
        )


def run_original_weights(thresholds_dict: dict, *, use_landmask: bool):
    """现场调用原算法 GenerateTopographicZoneWeights。"""
    from improver.generate_ancillaries.generate_topographic_zone_weights import (  # noqa: E402
        GenerateTopographicZoneWeights as OrigWeightsPlugin,
    )

    orography = iris.load_cube(
        str(RESOURCE_ROOT / "basic" / "input_orog.nc"), "surface_altitude"
    )
    landmask = None
    if use_landmask:
        landmask = iris.load_cube(
            str(RESOURCE_ROOT / "basic" / "input_land.nc"), "land_binary_mask"
        )
    return OrigWeightsPlugin()(
        orography.copy(),
        thresholds_dict,
        landmask=landmask.copy() if landmask is not None else None,
    )


def assert_matches_original_cube(result: xr.DataArray, original_cube) -> None:
    """比较迁移版结果与原算法 Iris Cube。"""
    result_core = result.squeeze(drop=True)
    if "level" in result_core.dims and "topographic_zone" not in result_core.dims:
        result_core = result_core.rename({"level": "topographic_zone"})

    np.testing.assert_allclose(
        _values_with_nan(result_core.values),
        _values_with_nan(original_cube.data),
        equal_nan=True,
        atol=1e-5,
        rtol=1e-5,
    )
    np.testing.assert_allclose(
        result_core.coords["topographic_zone"].values,
        np.asarray(original_cube.coord("topographic_zone").points),
    )


# 官方数据回归测试

@_requires_improver
@_requires_official_data
def test_official_basic_matches_kgo_and_original():
    """测试默认阈值加海陆掩码场景与 KGO、原算法结果一致。"""
    orography = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input_orog.nc")
    )
    landmask = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input_land.nc")
    )
    kgo = load_primary_dataarray(RESOURCE_ROOT / "basic" / "kgo.nc")
    original = run_original_weights(THRESHOLDS_DICT, use_landmask=True)

    result = GenerateTopographicZoneWeights().process(
        orography, THRESHOLDS_DICT, landmask=landmask
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)
    assert result.attrs["topographic_zones_include_seapoints"] == "False"


@_requires_improver
@_requires_official_data
def test_official_json_bounds_matches_kgo_and_original():
    """测试 JSON 阈值加海陆掩码场景与 KGO、原算法结果一致。"""
    orography = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input_orog.nc")
    )
    landmask = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input_land.nc")
    )
    thresholds = load_thresholds_from_json(RESOURCE_ROOT / "basic" / "bounds.json")
    kgo = load_primary_dataarray(
        RESOURCE_ROOT / "basic" / "kgo_from_json_bounds.nc"
    )
    original = run_original_weights(thresholds, use_landmask=True)

    result = GenerateTopographicZoneWeights().process(
        orography, thresholds, landmask=landmask
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)


@_requires_improver
@_requires_official_data
def test_official_without_landmask_matches_kgo_and_original():
    """测试默认阈值且不传海陆掩码时与 KGO、原算法结果一致。"""
    orography = to_meb6d_grid(
        load_primary_dataarray(RESOURCE_ROOT / "basic" / "input_orog.nc")
    )
    kgo = load_primary_dataarray(
        RESOURCE_ROOT / "basic_no_landsea_mask" / "kgo.nc"
    )
    original = run_original_weights(THRESHOLDS_DICT, use_landmask=False)

    result = GenerateTopographicZoneWeights().process(
        orography, THRESHOLDS_DICT, landmask=None
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)
    assert result.attrs["topographic_zones_include_seapoints"] == "True"


@_requires_improver
@_requires_multi_data
def test_official_multi_realization_r0_matches_kgo_and_original():
    """多成员样例取 realization/member=0，与 KGO、原算法一致。"""
    import meteva_base as meb
    from improver.generate_ancillaries.generate_topographic_zone_weights import (  # noqa: E402
        GenerateTopographicZoneWeights as OrigWeightsPlugin,
    )

    multi = RESOURCE_ROOT / "multi_realization"
    orography = meb.read_griddata_from_nc(str(multi / "cli_inputs" / "input_orog_meb.nc"))
    landmask = meb.read_griddata_from_nc(str(multi / "cli_inputs" / "input_land_meb.nc"))
    orography = orography.isel(member=[0])
    landmask = landmask.isel(member=[0])

    orog_cube = iris.load_cube(
        str(multi / "input_orog.nc"), "surface_altitude"
    ).extract(iris.Constraint(realization=0))
    land_cube = iris.load_cube(
        str(multi / "input_land.nc"), "land_binary_mask"
    ).extract(iris.Constraint(realization=0))

    kgo = load_primary_dataarray(multi / "kgo.nc")
    original = OrigWeightsPlugin()(
        orog_cube.copy(), THRESHOLDS_DICT, landmask=land_cube.copy()
    )

    result = GenerateTopographicZoneWeights().process(
        orography, THRESHOLDS_DICT, landmask=landmask
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)
