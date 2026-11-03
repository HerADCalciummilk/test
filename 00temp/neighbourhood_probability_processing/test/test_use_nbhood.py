#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""带掩码分层邻域处理的单元测试。"""

from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from neighbourhood_probability_processing.src.use_nbhood import ApplyNeighbourhoodProcessingWithAMask

def _find_existing_dir(candidates):
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


TEST_DATA_ROOT = (
    Path(__file__).resolve().parents[1]
    / "test_data"
    / "official_test_use_nbhood"
    / "iterate_with_mask"
)
INPUT_ROOT = _find_existing_dir(
    [
        TEST_DATA_ROOT / "cli_input",
        Path(__file__).resolve().parents[1] / "resource" / "official_test_use_nohood",
    ]
)
REFERENCE_ROOT = TEST_DATA_ROOT / "basic_collapse_bands"
_requires_official_data = pytest.mark.skipif(
    INPUT_ROOT is None
    or not (INPUT_ROOT / "thresholded_input.nc").is_file(),
    reason="未同步 test_data/official_test_use_nbhood",
)


def resolve_resource_file(filename: str) -> Path:
    """从参考结果目录读取 KGO / 原算法对照文件。"""
    path = REFERENCE_ROOT / filename
    if path.exists():
        return path
    raise FileNotFoundError(f"未找到测试文件: {filename}")


FILL_VALUE_THRESHOLD = 1.0e20


def make_dataarray(data):
    """构造标准 meb 六维测试 DataArray。"""
    values = np.asarray(data, dtype=np.float32)
    if values.ndim == 2:
        values = values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    elif values.ndim == 3:
        values = values[:, np.newaxis, np.newaxis, np.newaxis, :, :]
    else:
        raise ValueError("测试辅助函数仅支持 2D 或 3D 输入。")
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.arange(values.shape[0], dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array([np.datetime64("2024-01-01T00:00:00")]),
            "dtime": np.array([0], dtype=np.int32),
            "lat": xr.DataArray(
                np.arange(values.shape[-2], dtype=np.float32),
                dims=("lat",),
                attrs={"units": "m"},
            ),
            "lon": xr.DataArray(
                np.arange(values.shape[-1], dtype=np.float32),
                dims=("lon",),
                attrs={"units": "m"},
            ),
        },
        attrs={
            "units": "1",
            "model": "",
            "dtime_units": "hour",
            "level_type": "isobaric",
            "time_type": "UT",
            "time_bounds": np.array([0, 0], dtype=np.int32),
        },
    )


def make_mask_dataarray(mask):
    """构造带 topographic_zone 维的掩码 DataArray。"""
    values = np.asarray(mask, dtype=np.float32)
    return xr.DataArray(
        values,
        dims=("topographic_zone", "lat", "lon"),
        coords={
            "topographic_zone": [50.0, 100.0, 150.0],
            "lat": xr.DataArray(
                np.arange(values.shape[-2], dtype=np.float32),
                dims=("lat",),
                attrs={"units": "m"},
            ),
            "lon": xr.DataArray(
                np.arange(values.shape[-1], dtype=np.float32),
                dims=("lon",),
                attrs={"units": "m"},
            ),
        },
    )


def load_primary_dataarray(path: Path) -> xr.DataArray:
    """读取测试文件中的主变量。"""
    dataset = xr.open_dataset(path, decode_timedelta=False)
    for name, data_array in dataset.data_vars.items():
        if data_array.ndim >= 2 and "bnds" not in name and name != "lambert_azimuthal_equal_area":
            return data_array
    raise ValueError(f"未在 {path} 中找到主数据变量。")


def spatial_stack_from_meb6d(result) -> np.ndarray:
    """从六维结果提取与官方 ``(threshold,y,x)`` 对齐的堆叠场。

    阈值在 ``level`` 上时取 ``[0,:,0,0,:,:]``；集合在 ``member`` 上时取 ``[:,0,0,0,:,:]``。
    """
    arr = np.asarray(result.values if isinstance(result, xr.DataArray) else result)
    if arr.ndim != 6:
        return arr
    n_member, n_level = arr.shape[0], arr.shape[1]
    if n_member == 1 and n_level >= 1:
        return arr[0, :, 0, 0, :, :]
    return arr[:, 0, 0, 0, :, :]


def clean_fill_values(data):
    """将官方测试数据中的大填充值转换为 NaN。"""
    values = np.asarray(data, dtype=np.float64)
    cleaned = np.where(np.abs(values) >= FILL_VALUE_THRESHOLD, np.nan, values)
    return cleaned.astype(np.float32)


def clean_fill_values_as_dataarray(data_array: xr.DataArray) -> xr.DataArray:
    """保留坐标信息地清洗大填充值。"""
    return xr.DataArray(
        clean_fill_values(data_array),
        dims=data_array.dims,
        coords=data_array.coords,
        attrs=data_array.attrs.copy(),
    )


def test_process_without_collapse_matches_original_small_case():
    """测试未折叠场景下逐掩码分层输出与原算法小样例一致。"""
    data = np.array([[1, 1, 1], [1, 1, 0], [0, 0, 0]], dtype=np.float32)
    mask = np.array(
        [
            [[0, 1, 0], [1, 1, 0], [0, 0, 0]],
            [[0, 0, 1], [0, 0, 1], [1, 1, 0]],
            [[0, 0, 0], [0, 0, 0], [0, 0, 1]],
        ],
        dtype=np.float32,
    )
    expected = np.array(
        [
            [[1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]],
            [[np.nan, 0.5, 0.5], [0.0, 0.25, 0.33333334], [0.0, 0.0, 0.0]],
            [[np.nan, np.nan, np.nan], [np.nan, 0.0, 0.0], [np.nan, 0.0, 0.0]],
        ],
        dtype=np.float32,
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    ).process(data, mask, grid_spacing=1.0)

    assert result.shape == (3, 3, 3)
    np.testing.assert_allclose(result, expected, equal_nan=True)


def test_process_multileading_without_collapse():
    """测试多前导维输入时会在空间维之前插入掩码分层维。"""
    data = np.ones((2, 3, 3), dtype=np.float32)
    mask = np.ones((3, 3, 3), dtype=np.float32)

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    ).process(data, mask, grid_spacing=1.0)

    assert result.shape == (2, 3, 3, 3)
    np.testing.assert_allclose(result[0], result[1])


def test_process_with_collapse_weights():
    """测试提供分层权重时会沿掩码分层维做加权折叠。"""
    data = np.array([[1, 1, 1], [1, 1, 0], [0, 0, 0]], dtype=np.float32)
    mask = np.array(
        [
            [[0, 1, 0], [1, 1, 0], [0, 0, 0]],
            [[0, 0, 1], [0, 0, 1], [1, 1, 0]],
            [[0, 0, 0], [0, 0, 0], [0, 0, 1]],
        ],
        dtype=np.float32,
    )
    weights = np.array(
        [
            [[np.nan, 1, 0], [1, 0.5, 0], [0, 0, 0]],
            [[np.nan, 0, 1], [0, 0.5, 0.75], [0.75, 0.75, 0.5]],
            [[np.nan, 0, 0], [0, 0, 0.25], [0.25, 0.25, 0.5]],
        ],
        dtype=np.float32,
    )
    expected = np.ma.masked_array(
        [[np.nan, 1.0, 0.5], [1.0, 0.625, 0.25], [0.0, 0.0, 0.0]],
        mask=[[True, False, False], [False, False, False], [False, False, False]],
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0, collapse_weights=weights
    ).process(data, mask, grid_spacing=1.0)

    np.testing.assert_allclose(result.data, expected.data, equal_nan=True)
    np.testing.assert_array_equal(result.mask, expected.mask)


def test_collapse_weights_spatial_shape_mismatch_raises():
    """测试折叠权重空间维与数据不一致时会给出友好报错。"""
    data = np.ones((3, 3), dtype=np.float32)
    mask = np.ones((3, 3, 3), dtype=np.float32)
    weights = np.ones((3, 2, 2), dtype=np.float32)  # 空间维 (2,2) 与数据 (3,3) 不符

    plugin = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0, collapse_weights=weights
    )
    with pytest.raises(ValueError, match="空间形状"):
        plugin.process(data, mask, grid_spacing=1.0)


def test_collapse_weights_broadcastable_spatial_shape_raises():
    """测试权重某空间维为 1 时会被拦下，避免 np.broadcast_to 静默广播算错。"""
    data = np.ones((3, 3), dtype=np.float32)
    mask = np.ones((3, 3, 3), dtype=np.float32)
    weights = np.ones((3, 1, 3), dtype=np.float32)  # (1,3) 可广播到 (3,3)，但语义错误

    plugin = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0, collapse_weights=weights
    )
    with pytest.raises(ValueError, match="空间形状"):
        plugin.process(data, mask, grid_spacing=1.0)


def test_xarray_matches_numpy_without_collapse():
    """测试 xarray 与 numpy 在等价输入下结果一致。"""
    data = np.array([[1, 1, 1], [1, 1, 0], [0, 0, 0]], dtype=np.float32)
    mask = np.ones((3, 3, 3), dtype=np.float32)
    plugin_np = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    )
    plugin_xr = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    )

    result_np = plugin_np.process(data, mask, grid_spacing=1.0)
    result_xr = plugin_xr.process(make_dataarray(data), make_mask_dataarray(mask))

    assert isinstance(result_xr, xr.DataArray)
    assert result_xr.dims == ("member", "level", "time", "dtime", "lat", "lon")
    # member 仍为输入集合；地形带并入 level
    assert result_xr.sizes["member"] == 1
    assert result_xr.sizes["level"] == 3
    np.testing.assert_allclose(result_np, result_xr.values[0, :, 0, 0, :, :])
    np.testing.assert_allclose(result_xr.coords["threshold"].values, [0.0, 0.0, 0.0])
    np.testing.assert_allclose(
        result_xr.coords["topographic_zone"].values, [50.0, 100.0, 150.0]
    )
    assert result_xr.attrs.get("is_threshold_zone_stacked") == "True"
    assert result_xr.attrs.get("threshold_zone_stack_dims") == "threshold,topographic_zone"


def test_xarray_result_preserves_masking_dimension_coord():
    """测试 xarray 未折叠输出会并入 level 并保留映射坐标。"""
    data = make_dataarray(np.ones((2, 3, 3), dtype=np.float32))
    mask = make_mask_dataarray(np.ones((3, 3, 3), dtype=np.float32))

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    ).process(data, mask)

    assert isinstance(result, xr.DataArray)
    assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert result.sizes["member"] == data.sizes["member"]
    assert result.sizes["level"] == data.sizes["level"] * 3
    assert "threshold" in result.coords
    assert "topographic_zone" in result.coords
    assert result.attrs.get("is_threshold_zone_stacked") == "True"
    assert "topographic_zone" not in result.dims


def test_xarray_stacked_coords_threshold_times_zone():
    """多阈值×多地形带时，辅助坐标记录笛卡尔积语义。"""
    values = np.ones((1, 2, 1, 1, 3, 3), dtype=np.float32)
    data = xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": [0],
            "level": [1.0, 2.0],
            "time": [np.datetime64("2024-01-01T00:00:00")],
            "dtime": [0],
            "lat": xr.DataArray(
                np.arange(3, dtype=np.float32), dims=("lat",), attrs={"units": "m"}
            ),
            "lon": xr.DataArray(
                np.arange(3, dtype=np.float32), dims=("lon",), attrs={"units": "m"}
            ),
        },
        attrs={"units": "1"},
    )
    mask = xr.DataArray(
        np.ones((2, 3, 3), dtype=np.float32),
        dims=("topographic_zone", "lat", "lon"),
        coords={
            "topographic_zone": [10.0, 20.0],
            "lat": data.lat,
            "lon": data.lon,
        },
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0
    ).process(data, mask)

    assert result.sizes["level"] == 4
    np.testing.assert_allclose(
        result.coords["threshold"].values, [1.0, 1.0, 2.0, 2.0]
    )
    np.testing.assert_allclose(
        result.coords["topographic_zone"].values, [10.0, 20.0, 10.0, 20.0]
    )


def test_xarray_collapsed_result_uses_input_dimensions():
    """测试 xarray 折叠输出会恢复为原输入维度。"""
    data = make_dataarray(np.ones((3, 3), dtype=np.float32))
    mask = make_mask_dataarray(np.ones((3, 3, 3), dtype=np.float32))
    weights = xr.DataArray(
        np.ones((3, 3, 3), dtype=np.float32),
        dims=("topographic_zone", "lat", "lon"),
        coords=mask.coords,
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone", "square", 1.0, collapse_weights=weights
    ).process(data, mask)

    assert isinstance(result, xr.DataArray)
    assert result.dims == data.dims
    assert "topographic_zone" not in result.dims


def test_mask_requires_masking_dimension_for_xarray():
    """测试 xarray 掩码缺少指定分层维时会报错。"""
    data = make_dataarray(np.ones((3, 3), dtype=np.float32))
    mask = xr.DataArray(
        np.ones((3, 3, 3), dtype=np.float32),
        dims=("band", "lat", "lon"),
        coords={"lat": data.lat, "lon": data.lon},
    )
    plugin = ApplyNeighbourhoodProcessingWithAMask("topographic_zone", "square", 1.0)

    with pytest.raises(ValueError, match="topographic_zone"):
        plugin.process(data, mask)


def test_numpy_multilead_radii_are_applied_per_slice():
    """测试多切片 numpy 输入会按各自时效使用对应半径。"""
    data = np.ones((2, 5, 5), dtype=np.float32)
    mask = np.ones((1, 5, 5), dtype=np.float32)
    plugin = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone",
        "square",
        radii=[1.0, 2.0],
        lead_times=[1.0, 2.0],
        sum_only=True,
    )

    result = plugin.process(
        data, mask, input_lead_times=np.array([1.0, 2.0]), grid_spacing=1.0
    )

    assert result.shape == (2, 1, 5, 5)
    np.testing.assert_allclose(result[0, 0, 2, 2], 9.0)
    np.testing.assert_allclose(result[1, 0, 2, 2], 25.0)


@_requires_official_data
def test_official_use_nbhood_square_matches_kgo_and_original():
    """测试官方方形 use_nbhood 样例与 KGO 和原算法折叠结果一致。"""
    input_data = load_primary_dataarray(INPUT_ROOT / "thresholded_input.nc")
    mask_data = load_primary_dataarray(INPUT_ROOT / "orographic_bands_mask.nc")
    weights_data = clean_fill_values_as_dataarray(
        load_primary_dataarray(INPUT_ROOT / "orographic_bands_weights.nc")
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "level",
        "square",
        10000.0,
        collapse_weights=weights_data,
    ).process(input_data, mask_data)

    kgo = clean_fill_values(load_primary_dataarray(resolve_resource_file("kgo_collapsed.nc")))
    original = clean_fill_values(
        load_primary_dataarray(resolve_resource_file("original_collapsed.nc"))
    )

    actual = spatial_stack_from_meb6d(result)
    np.testing.assert_allclose(actual, kgo, equal_nan=True, atol=1.0e-6)
    np.testing.assert_allclose(actual, original, equal_nan=True, atol=1.0e-6)


@_requires_official_data
def test_official_use_nbhood_circular_matches_kgo_and_original():
    """测试官方圆形 use_nbhood 样例与 KGO 和原算法折叠结果一致。"""
    input_data = load_primary_dataarray(INPUT_ROOT / "thresholded_input.nc")
    mask_data = load_primary_dataarray(INPUT_ROOT / "orographic_bands_mask.nc")
    weights_data = clean_fill_values_as_dataarray(
        load_primary_dataarray(INPUT_ROOT / "orographic_bands_weights.nc")
    )

    result = ApplyNeighbourhoodProcessingWithAMask(
        "level",
        "circular",
        10000.0,
        collapse_weights=weights_data,
    ).process(input_data, mask_data)

    kgo = clean_fill_values(
        load_primary_dataarray(resolve_resource_file("kgo_collapsed_circular.nc"))
    )
    original = clean_fill_values(
        load_primary_dataarray(resolve_resource_file("original_collapsed_circular.nc"))
    )

    actual = spatial_stack_from_meb6d(result)
    np.testing.assert_allclose(actual, kgo, equal_nan=True, atol=1.0e-6)
    np.testing.assert_allclose(actual, original, equal_nan=True, atol=1.0e-6)


@_requires_official_data
def test_meb6d_level_mask_weights_match_generate_plugins_and_collapse():
    """Generate* 六维 meb（level 带维）可直接喂给 ApplyNeighbourhood 并与官方折叠一致。"""
    import meteva_base as meb
    from generate_ancillary.src.generate_ancillary import GenerateOrographyBandAncils
    from generate_ancillary.src.generate_topographic_zone_weights import (
        GenerateTopographicZoneWeights,
    )

    orog = meb.read_griddata_from_nc(
        str(
            Path(__file__).resolve().parents[2]
            / "generate_ancillary"
            / "test_data"
            / "generate-topography-bands-weights"
            / "basic"
            / "cli_inputs"
            / "input_orog_meb.nc"
        )
    )
    land = meb.read_griddata_from_nc(
        str(
            Path(__file__).resolve().parents[2]
            / "generate_ancillary"
            / "test_data"
            / "generate-topography-bands-weights"
            / "basic"
            / "cli_inputs"
            / "input_land_meb.nc"
        )
    )
    orog = orog.copy(deep=True)
    orog.attrs["units"] = "m"
    orog.coords["lat"].attrs["units"] = "m"
    orog.coords["lon"].attrs["units"] = "m"
    land = land.copy(deep=True)
    land.coords["lat"].attrs["units"] = "m"
    land.coords["lon"].attrs["units"] = "m"

    thresholds = {
        "bounds": [[-500.0, 150.0], [150.0, 300.0], [300.0, 10000.0]],
        "units": "m",
    }
    mask_6d = GenerateOrographyBandAncils().process(orog, thresholds, land)
    weights_6d = GenerateTopographicZoneWeights().process(orog, thresholds, land)
    assert mask_6d.dims == ("member", "level", "time", "dtime", "lat", "lon")
    assert int(mask_6d.sizes["level"]) == 3

    input_data = load_primary_dataarray(INPUT_ROOT / "thresholded_input.nc")
    result = ApplyNeighbourhoodProcessingWithAMask(
        "level",
        "square",
        10000.0,
        collapse_weights=weights_6d,
    ).process(input_data, mask_6d)

    kgo = clean_fill_values(load_primary_dataarray(resolve_resource_file("kgo_collapsed.nc")))
    actual = spatial_stack_from_meb6d(result)
    np.testing.assert_allclose(actual, kgo, equal_nan=True, atol=1.0e-6)


def _make_geographic_meb(spatial_2d: np.ndarray) -> xr.DataArray:
    """构造等距经纬六维测试场。"""
    values = np.asarray(spatial_2d, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("仅支持二维空间场")
    n_lat, n_lon = values.shape
    return xr.DataArray(
        values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :],
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array([0], dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array([np.datetime64("2024-01-01T00:00:00")]),
            "dtime": np.array([0], dtype=np.int32),
            "lat": xr.DataArray(
                30.0 + np.arange(n_lat, dtype=np.float64) * 0.01,
                dims=("lat",),
                attrs={"units": "degree_north"},
            ),
            "lon": xr.DataArray(
                110.0 + np.arange(n_lon, dtype=np.float64) * 0.01,
                dims=("lon",),
                attrs={"units": "degree_east"},
            ),
        },
        attrs={"units": "1"},
    )


def _make_geographic_band_mask(mask_3d: np.ndarray) -> xr.DataArray:
    """构造经纬坐标下的 topographic_zone 掩码。"""
    values = np.asarray(mask_3d, dtype=np.float32)
    n_zone, n_lat, n_lon = values.shape
    return xr.DataArray(
        values,
        dims=("topographic_zone", "lat", "lon"),
        coords={
            "topographic_zone": np.arange(n_zone, dtype=np.float32) * 50.0 + 50.0,
            "lat": xr.DataArray(
                30.0 + np.arange(n_lat, dtype=np.float64) * 0.01,
                dims=("lat",),
                attrs={"units": "degree_north"},
            ),
            "lon": xr.DataArray(
                110.0 + np.arange(n_lon, dtype=np.float64) * 0.01,
                dims=("lon",),
                attrs={"units": "degree_east"},
            ),
        },
    )


def test_use_nbhood_geographic_matches_adapted_laea_path():
    """ApplyNeighbourhoodProcessingWithAMask：经纬完整路径 ≡ 适配 LAEA 投影路径。"""
    from neighbourhood_probability_processing.src.utils._regrid import prepare_geographic_input

    values = np.arange(5 * 5, dtype=np.float32).reshape(5, 5)
    data = _make_geographic_meb(values)
    mask = _make_geographic_band_mask(
        np.stack(
            [
                np.ones((5, 5), dtype=np.float32),
                np.zeros((5, 5), dtype=np.float32),
                np.zeros((5, 5), dtype=np.float32),
            ],
            axis=0,
        )
    )
    # 仅第 0 带有效，便于折叠
    weights = mask.copy(deep=True)
    weights.data = np.where(mask.values > 0, 1.0, np.nan).astype(np.float32)

    plugin = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone",
        "square",
        2000.0,
        collapse_weights=weights,
    )
    result_geo = plugin.process(data, mask)

    projected, projected_mask, ctx = prepare_geographic_input(data, mask)
    assert ctx is not None
    # 权重随同一 ctx 换到米轴（场值不变，仅坐标）
    from neighbourhood_probability_processing.src.utils._regrid import regrid_dataarray_to_projected

    weights_proj = regrid_dataarray_to_projected(weights, ctx)
    plugin_proj = ApplyNeighbourhoodProcessingWithAMask(
        "topographic_zone",
        "square",
        2000.0,
        collapse_weights=weights_proj,
    )
    result_on_laea = plugin_proj.process(projected, projected_mask)

    np.testing.assert_allclose(
        np.asarray(result_geo.values, dtype=np.float64),
        np.asarray(result_on_laea.values, dtype=np.float64),
        equal_nan=True,
        atol=0.0,
        rtol=0.0,
    )
    np.testing.assert_array_equal(result_geo.coords["lat"].values, data.coords["lat"].values)
    np.testing.assert_array_equal(result_geo.coords["lon"].values, data.coords["lon"].values)
