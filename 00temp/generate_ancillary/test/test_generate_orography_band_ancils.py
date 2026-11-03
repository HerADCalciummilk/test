#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""GenerateOrographyBandAncils 单元测试。"""

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

from generate_ancillary.src.generate_ancillary import (  # noqa: E402
    THRESHOLDS_DICT,
    GenerateOrographyBandAncils,
)

RESOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "generate-topography-bands-mask"
)

_requires_official_data = pytest.mark.skipif(
    not (RESOURCE_ROOT / "basic" / "input_orog.nc").is_file(),
    reason="未同步 test_data/generate-topography-bands-mask",
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


def make_landmask_numpy(data=None):
    """构造基础海陆掩码数组。"""
    if data is None:
        data = np.array([[1, 0, 0], [1, 0, 0], [1, 1, 1]], dtype=np.int8)
    return np.asarray(data, dtype=np.int8)


def make_orography_numpy(data=None):
    """构造基础地形高度数组。"""
    if data is None:
        data = np.array(
            [[10.0, 0.0, 0.0], [20.0, 100.0, 15.0], [-10.0, 100.0, 40.0]],
            dtype=np.float32,
        )
    return np.asarray(data, dtype=np.float32)


def make_orography_xarray(data=None):
    """构造带米单位与空间坐标的地形 DataArray。"""
    values = make_orography_numpy(data)
    return xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": xr.DataArray(
                np.array([0.0, 1000.0, 2000.0], dtype=np.float32),
                dims=("y",),
                attrs={"units": "m"},
            ),
            "x": xr.DataArray(
                np.array([0.0, 1000.0, 2000.0], dtype=np.float32),
                dims=("x",),
                attrs={"units": "m"},
            ),
        },
        attrs={"units": "m"},
        name="orography",
    )


def make_landmask_xarray(data=None):
    """构造带空间坐标的海陆掩码 DataArray。"""
    values = make_landmask_numpy(data)
    return xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": xr.DataArray(
                np.array([0.0, 1000.0, 2000.0], dtype=np.float32),
                dims=("y",),
                attrs={"units": "m"},
            ),
            "x": xr.DataArray(
                np.array([0.0, 1000.0, 2000.0], dtype=np.float32),
                dims=("x",),
                attrs={"units": "m"},
            ),
        },
        name="land_binary_mask",
    )


def make_orography_meb6d() -> xr.DataArray:
    """构造 meteva_base 风格 6 维地形场。"""
    base = make_orography_numpy()
    values = base[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": xr.DataArray(np.array(["m00"]), dims=("member",)),
            "level": xr.DataArray(np.array([0], dtype=np.int32), dims=("level",)),
            "time": xr.DataArray(
                np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
                dims=("time",),
            ),
            "dtime": xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",)),
            "lat": xr.DataArray(np.array([0.0, 1.0, 2.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(np.array([100.0, 101.0, 102.0], dtype=np.float32), dims=("lon",)),
        },
        attrs={"units": "m"},
        name="orography",
    )


def make_landmask_lat_lon() -> xr.DataArray:
    """构造仅含 lat/lon 的海陆掩码，用于测试广播。"""
    values = make_landmask_numpy()
    return xr.DataArray(
        values,
        dims=("lat", "lon"),
        coords={
            "lat": xr.DataArray(np.array([0.0, 1.0, 2.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(np.array([100.0, 101.0, 102.0], dtype=np.float32), dims=("lon",)),
        },
        name="land_binary_mask",
    )


def make_landmask_meb6d() -> xr.DataArray:
    """构造与 make_orography_meb6d 对齐的六维海陆掩码。"""
    base = make_landmask_numpy()
    values = base[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": xr.DataArray(np.array(["m00"]), dims=("member",)),
            "level": xr.DataArray(np.array([0], dtype=np.int32), dims=("level",)),
            "time": xr.DataArray(
                np.array(["2024-01-01T00:00:00"], dtype="datetime64[ns]"),
                dims=("time",),
            ),
            "dtime": xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",)),
            "lat": xr.DataArray(np.array([0.0, 1.0, 2.0], dtype=np.float32), dims=("lat",)),
            "lon": xr.DataArray(np.array([100.0, 101.0, 102.0], dtype=np.float32), dims=("lon",)),
        },
        name="land_binary_mask",
    )


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


def assert_matches_reference(result: xr.DataArray, expected: xr.DataArray) -> None:
    """比较迁移版结果与参考结果的数值和关键地形带坐标。"""
    # 迁移版 process 输出为六维，官方参考数据为 topographic_zone + 二维空间。
    result_core = result.squeeze(drop=True)
    if "level" in result_core.dims and "topographic_zone" not in result_core.dims:
        result_core = result_core.rename({"level": "topographic_zone"})

    np.testing.assert_array_equal(result_core.values, expected.values)
    np.testing.assert_allclose(
        result_core.coords["topographic_zone"].values,
        expected.coords["topographic_zone"].values,
    )
    if "topographic_zone_bnds" in expected.coords:
        lower_name = (
            "level_lower_bound"
            if "level_lower_bound" in result.coords
            else "topographic_zone_lower_bound"
        )
        upper_name = (
            "level_upper_bound"
            if "level_upper_bound" in result.coords
            else "topographic_zone_upper_bound"
        )
        np.testing.assert_allclose(
            result.coords[lower_name].values,
            expected.coords["topographic_zone_bnds"].values[:, 0],
        )
        np.testing.assert_allclose(
            result.coords[upper_name].values,
            expected.coords["topographic_zone_bnds"].values[:, 1],
        )


def run_original_bands(thresholds_dict: dict, *, use_landmask: bool):
    """现场调用原算法（与 run_generate_ancillary_to_result.py 一致：process → concatenate_cube）。"""
    from improver.generate_ancillaries.generate_ancillary import (  # noqa: E402
        GenerateOrographyBandAncils as OrigBandsPlugin,
    )

    orography = iris.load_cube(
        str(RESOURCE_ROOT / "basic" / "input_orog.nc"), "surface_altitude"
    )
    landmask = None
    if use_landmask:
        landmask = iris.load_cube(
            str(RESOURCE_ROOT / "basic" / "input_land.nc"), "land_binary_mask"
        )
    return (
        OrigBandsPlugin()
        .process(
            orography.copy(),
            thresholds_dict,
            landmask=landmask.copy() if landmask is not None else None,
        )
        .concatenate_cube()
    )


def assert_matches_original_cube(result: xr.DataArray, original_cube) -> None:
    """比较迁移版结果与原算法 Iris Cube 的数值与地形带中心。"""
    result_core = result.squeeze(drop=True)
    if "level" in result_core.dims and "topographic_zone" not in result_core.dims:
        result_core = result_core.rename({"level": "topographic_zone"})

    np.testing.assert_array_equal(result_core.values, np.asarray(original_cube.data))
    np.testing.assert_allclose(
        result_core.coords["topographic_zone"].values,
        np.asarray(original_cube.coord("topographic_zone").points),
    )


# 基础单元测试

def test_sea_mask_returns_masked_array_by_default():
    """测试默认海点处理会返回 masked array。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.sea_mask(make_landmask_numpy(), make_orography_numpy())

    expected_data = np.array(
        [[10.0, 1.0e20, 1.0e20], [20.0, 1.0e20, 1.0e20], [-10.0, 100.0, 40.0]]
    )
    expected_mask = np.array(
        [[False, True, True], [False, True, True], [False, False, False]]
    )
    np.testing.assert_allclose(result.data, expected_data, rtol=1e-6)
    np.testing.assert_array_equal(result.mask, expected_mask)


def test_sea_mask_returns_plain_array_when_fill_value_given():
    """测试指定海点填充值时不再返回 masked array。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.sea_mask(
        make_landmask_numpy(), make_orography_numpy(), sea_fill_value=0
    )

    expected = np.array([[10.0, 0.0, 0.0], [20.0, 0.0, 0.0], [-10.0, 100.0, 40.0]])
    np.testing.assert_array_equal(result, expected)
    assert not np.ma.isMaskedArray(result)


def test_gen_orography_masks_for_land_band_numpy():
    """测试 numpy 输入下单个地形带结果正确。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.gen_orography_masks(
        make_orography_numpy(), make_landmask_numpy(), [0, 50]
    )

    expected = np.array([[[1, 0, 0], [1, 0, 0], [0, 0, 1]]], dtype=np.int32)
    np.testing.assert_array_equal(result, expected)


def test_gen_orography_masks_keeps_metadata_for_xarray():
    """测试 xarray 输入下会写出地形带元数据。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.gen_orography_masks(
        make_orography_meb6d(), make_landmask_meb6d(), [-10, 10]
    )

    expected = np.array(
        [[[[[1, 0, 0], [0, 0, 0], [0, 0, 0]]]]], dtype=np.int32
    )
    expected = expected[np.newaxis, ...]
    np.testing.assert_array_equal(result.values, expected)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    np.testing.assert_allclose(
        result.coords["level"].values, np.array([0.0])
    )
    np.testing.assert_allclose(
        result.coords["level_lower_bound"].values,
        np.array([-10.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        result.coords["level_upper_bound"].values,
        np.array([10.0], dtype=np.float32),
    )
    assert result.attrs["units"] == "1"
    assert result.attrs["topographic_zones_include_seapoints"] == "False"


def test_gen_orography_masks_without_landmask_marks_sea_points_included():
    """测试未提供海陆掩码时会标记包含海点。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.gen_orography_masks(make_orography_meb6d(), None, [-10, 10])

    expected = np.array(
        [[[[[1, 1, 1], [0, 0, 0], [0, 0, 0]]]]], dtype=np.int32
    )
    expected = expected[np.newaxis, ...]
    np.testing.assert_array_equal(result.values, expected)
    assert result.attrs["topographic_zones_include_seapoints"] == "True"


def test_gen_orography_masks_supports_threshold_unit_conversion():
    """测试阈值单位可以换算到地形高度单位。"""
    plugin = GenerateOrographyBandAncils()
    result = plugin.gen_orography_masks(
        make_orography_meb6d(), make_landmask_meb6d(), [0, 0.05], units="km"
    )

    expected = np.array(
        [[[[[1, 0, 0], [1, 0, 0], [0, 0, 1]]]]], dtype=np.int32
    )
    expected = expected[np.newaxis, ...]
    np.testing.assert_array_equal(result.values, expected)
    assert result.coords["level"].attrs["units"] == "m"


def test_process_supports_meb6d_orography_and_numpy_landmask():
    """测试 6 维地形场与 numpy 海陆掩码可正确广播并输出。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}
    result = plugin.process(
        make_orography_meb6d(), thresholds, landmask=make_landmask_numpy()
    )

    expected = np.array(
        [
            [[[[0, 0, 0], [0, 0, 0], [0, 0, 0]]]],
            [[[[1, 0, 0], [1, 0, 0], [0, 0, 1]]]],
        ],
        dtype=np.int32,
    )
    expected = expected[np.newaxis, ...]
    np.testing.assert_array_equal(result.values, expected)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.attrs["topographic_zones_include_seapoints"] == "False"


def test_process_rejects_non_meb6d_xarray_landmask():
    """测试 xarray 海陆掩码若非六维格式会被拒绝。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}
    with pytest.raises(ValueError, match="griddata dims must be"):
        plugin.process(
            make_orography_meb6d(),
            thresholds,
            landmask=make_landmask_lat_lon(),
        )


def test_process_stacks_all_topographic_bands_for_xarray():
    """测试 process 会沿 topographic_zone 维堆叠所有地形带。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}

    result = plugin.process(
        make_orography_meb6d(), thresholds, landmask=make_landmask_meb6d()
    )

    expected = np.array(
        [
            [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            [[1, 0, 0], [1, 0, 0], [0, 0, 1]],
        ],
        dtype=np.int32,
    )
    np.testing.assert_array_equal(result.squeeze(drop=True).values, expected)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    np.testing.assert_allclose(
        result.coords["level"].values, np.array([-5.0, 25.0])
    )


def test_process_stacks_all_topographic_bands_for_numpy():
    """测试 numpy 输入下会返回按地形带堆叠的数组。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}

    result = plugin.process(
        make_orography_numpy(), thresholds, landmask=make_landmask_numpy()
    )

    expected = np.array(
        [
            [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            [[1, 0, 0], [1, 0, 0], [0, 0, 1]],
        ],
        dtype=np.int32,
    )
    np.testing.assert_array_equal(result, expected)


def test_process_raises_if_units_missing_in_thresholds_dict():
    """测试缺少 units 字段时会抛出 KeyError。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]]}

    with pytest.raises(KeyError, match="units"):
        plugin.process(
            make_orography_meb6d(),
            thresholds,
            landmask=make_landmask_meb6d(),
        )


def test_process_raises_if_bounds_missing_or_empty():
    """测试缺少 bounds 或 bounds 为空时会抛出 ValueError。"""
    plugin = GenerateOrographyBandAncils()
    thresholds_missing_bounds = {"units": "m"}
    thresholds_empty_bounds = {"bounds": [], "units": "m"}

    with pytest.raises(ValueError, match="未提供任何地形带阈值"):
        plugin.process(
            make_orography_meb6d(),
            thresholds_missing_bounds,
            landmask=make_landmask_meb6d(),
        )
    with pytest.raises(ValueError, match="未提供任何地形带阈值"):
        plugin.process(
            make_orography_meb6d(),
            thresholds_empty_bounds,
            landmask=make_landmask_meb6d(),
        )


def test_call_matches_process_for_generate_orography_band_ancils():
    """测试 __call__ 与 process 的输出完全一致。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}

    result_process = plugin.process(
        make_orography_meb6d(), thresholds, landmask=make_landmask_meb6d()
    )
    result_call = plugin(
        make_orography_meb6d(), thresholds, landmask=make_landmask_meb6d()
    )

    xr.testing.assert_identical(result_call, result_process)


def test_xarray_and_numpy_results_are_equivalent():
    """测试等价输入下 xarray 与 numpy 结果一致。"""
    plugin = GenerateOrographyBandAncils()
    thresholds = {"bounds": [[-10, 0], [0, 50]], "units": "m"}

    result_xarray = plugin.process(
        make_orography_meb6d(), thresholds, landmask=make_landmask_meb6d()
    )
    result_numpy = plugin.process(
        make_orography_numpy(), thresholds, landmask=make_landmask_numpy()
    )

    np.testing.assert_array_equal(result_xarray.squeeze(drop=True).values, result_numpy)


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
    original = run_original_bands(THRESHOLDS_DICT, use_landmask=True)

    result = GenerateOrographyBandAncils().process(
        orography, THRESHOLDS_DICT, landmask=landmask
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)


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
    kgo = load_primary_dataarray(RESOURCE_ROOT / "basic" / "kgo_from_json_bounds.nc")
    original = run_original_bands(thresholds, use_landmask=True)

    result = GenerateOrographyBandAncils().process(
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
    kgo = load_primary_dataarray(RESOURCE_ROOT / "basic_no_landsea_mask" / "kgo.nc")
    original = run_original_bands(THRESHOLDS_DICT, use_landmask=False)

    result = GenerateOrographyBandAncils().process(
        orography, THRESHOLDS_DICT, landmask=None
    )

    assert_matches_reference(result, kgo)
    assert_matches_original_cube(result, original)
    assert result.attrs["topographic_zones_include_seapoints"] == "True"
