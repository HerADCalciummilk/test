#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""nbhood 模块单元测试。"""

from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from neighbourhood_probability_processing.src.nbhood import (
    BaseNeighbourhoodProcessing,
    GeneratePercentilesFromANeighbourhood,
    NeighbourhoodProcessing,
    check_radius_against_distance,
    circular_kernel,
)
def _find_existing_dir(candidates):
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


RESOURCE_ROOT = _find_existing_dir(
    [
        Path(__file__).resolve().parents[1]
        / "test_data"
        / "official_test_nbhood",
        Path(__file__).resolve().parents[1] / "resource" / "official_test_nohood",
    ]
)
CLI_INPUT_ROOT = (RESOURCE_ROOT / "cli_input") if RESOURCE_ROOT is not None else None
FILL_VALUE_THRESHOLD = 1.0e20
_requires_official_data = pytest.mark.skipif(
    RESOURCE_ROOT is None
    or CLI_INPUT_ROOT is None
    or not (CLI_INPUT_ROOT / "basic" / "input.nc").is_file(),
    reason="未同步 test_data/official_test_nbhood",
)


def make_dataarray(data, dtime_values=None):
    """构造标准 meb 六维测试 DataArray。"""
    values = np.asarray(data, dtype=np.float32)
    if dtime_values is not None:
        dtime_arr = np.asarray(dtime_values, dtype=np.float32)
        if values.ndim == 2:
            values = np.repeat(
                values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :],
                len(dtime_arr),
                axis=3,
            )
        elif values.ndim == 3:
            values = np.repeat(
                values[:, np.newaxis, np.newaxis, np.newaxis, :, :],
                len(dtime_arr),
                axis=3,
            )
        else:
            raise ValueError("带 dtime_values 时测试辅助函数仅支持 2D 或 3D 输入。")
    elif values.ndim == 2:
        values = values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    elif values.ndim == 3:
        values = values[:, np.newaxis, np.newaxis, np.newaxis, :, :]
    else:
        raise ValueError("测试辅助函数仅支持 2D 或 3D 输入。")

    member_size = values.shape[0]
    lat_size = values.shape[-2]
    lon_size = values.shape[-1]
    if dtime_values is None:
        dtime_coord = xr.DataArray(np.array([0], dtype=np.int32), dims=("dtime",))
    else:
        dtime_coord = xr.DataArray(
            dtime_arr,
            dims=("dtime",),
            attrs={"units": "hours"},
        )
    coords = {
        "member": np.arange(member_size, dtype=np.int32),
        "level": np.array([0.0], dtype=np.float32),
        "time": np.array([np.datetime64("2024-01-01T00:00:00")]),
        "dtime": dtime_coord,
        "lat": xr.DataArray(
            np.arange(lat_size, dtype=np.float32) * 1000.0,
            dims=("lat",),
            attrs={"units": "m"},
        ),
        "lon": xr.DataArray(
            np.arange(lon_size, dtype=np.float32) * 1000.0,
            dims=("lon",),
            attrs={"units": "m"},
        ),
    }
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords=coords,
    )


def make_geographic_dataarray(
    spatial_values: np.ndarray, *, with_units: bool = True
) -> xr.DataArray:
    """构造等距经纬 meb 六维测试 DataArray。"""
    values = np.asarray(spatial_values, dtype=np.float32)
    if values.ndim == 2:
        values = values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    lat_size, lon_size = values.shape[-2], values.shape[-1]
    base_lat = 30.0
    base_lon = 110.0
    step = 0.01
    lat_attrs = {"units": "degree_north"} if with_units else {}
    lon_attrs = {"units": "degree_east"} if with_units else {}
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array([0], dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array([np.datetime64("2024-01-01T00:00:00")]),
            "dtime": np.array([0], dtype=np.int32),
            "lat": xr.DataArray(
                base_lat + np.arange(lat_size, dtype=np.float64) * step,
                dims=("lat",),
                attrs=lat_attrs,
            ),
            "lon": xr.DataArray(
                base_lon + np.arange(lon_size, dtype=np.float64) * step,
                dims=("lon",),
                attrs=lon_attrs,
            ),
        },
        attrs={"units": "1"},
    )


def load_primary_dataarray(path: Path) -> xr.DataArray:
    """读取测试文件中的主变量。"""
    dataset = xr.open_dataset(path, decode_timedelta=False)
    for name, data_array in dataset.data_vars.items():
        if data_array.ndim >= 2 and "bnds" not in name and name != "lambert_azimuthal_equal_area":
            return data_array
    raise ValueError(f"未在 {path} 中找到主数据变量。")


def clean_fill_values(data):
    """将官方测试数据中的大填充值转换为 NaN。"""
    values = np.asarray(data, dtype=np.float64)
    cleaned = np.where(np.abs(values) >= FILL_VALUE_THRESHOLD, np.nan, values)
    return cleaned.astype(np.float32)


def mask_fill_values(data):
    """将官方测试数据中的大填充值转换为 masked 值。"""
    values = np.asarray(data, dtype=np.float32)
    masked = np.ma.masked_invalid(values)
    return np.ma.masked_where(np.abs(np.ma.filled(masked, 0.0)) >= FILL_VALUE_THRESHOLD, masked)


def valid_mask_from_external(mask) -> np.ndarray:
    """外部掩码中有效格点（``mask != 0``）。"""
    return np.asarray(mask) != 0


def align_result_to_reference(result, reference) -> tuple[np.ndarray, np.ndarray]:
    """将六维算法输出与官方参考场对齐到同一形状。

    参考场常为 ``(threshold, y, x)`` 或 ``(realization, percentile, y, x)``；
    六维结果按 ``member`` / ``level`` 维切片后与参考对齐。
    """
    result_arr = (
        np.asarray(result.values)
        if isinstance(result, xr.DataArray)
        else (np.ma.getdata(result) if np.ma.isMaskedArray(result) else np.asarray(result))
    )
    ref_arr = np.asarray(reference)
    if result_arr.shape == ref_arr.shape:
        return result_arr, ref_arr
    if result_arr.ndim == 6:
        n_member, n_level = result_arr.shape[0], result_arr.shape[1]
        if ref_arr.ndim == 4 and n_level > 1:
            # 百分位邻域：(member, level=percentile, time, dtime, y, x)
            sliced = result_arr[:, :, 0, 0, :, :]
        elif n_member == 1 and n_level >= 1:
            sliced = result_arr[0, :, 0, 0, :, :]
        else:
            sliced = result_arr[:, 0, 0, 0, :, :]
        if sliced.shape == ref_arr.shape:
            return sliced, ref_arr
        if sliced.size == ref_arr.size:
            return sliced.reshape(ref_arr.shape), ref_arr
    raise ValueError(
        f"无法对齐测试数组形状: result={result_arr.shape}, reference={ref_arr.shape}"
    )


def spatial_array_from_six_dim(data) -> np.ndarray:
    """提取六维网格中的空间切片数组。"""
    arr = np.asarray(data.values if isinstance(data, xr.DataArray) else data)
    if arr.ndim == 6:
        n_member, n_level = arr.shape[0], arr.shape[1]
        if n_member == 1 and n_level >= 1:
            return arr[0, :, 0, 0, :, :]
        return arr[:, 0, 0, 0, :, :]
    return arr


def assert_allclose_at_valid(
    result,
    reference,
    *,
    valid: np.ndarray,
    atol: float = 1.0e-6,
) -> None:
    """仅在有效格点上比较数值（掩码位可保留邻域统计，不与参考 NaN 比）。"""
    result_arr, ref_arr = align_result_to_reference(result, reference)
    valid = np.asarray(valid.values if isinstance(valid, xr.DataArray) else valid)
    if valid.ndim == 6 and result_arr.ndim == 3:
        valid = valid[:, 0, 0, 0, :, :]
    elif valid.ndim == 6 and result_arr.ndim == 4:
        valid = valid[:, 0, 0, 0, :, :]
    valid = np.broadcast_to(valid, result_arr.shape)
    np.testing.assert_allclose(result_arr[valid], ref_arr[valid], atol=atol, rtol=0)


class TestBaseNeighbourhoodProcessing:
    """测试基类功能：半径管理、时效插值、输入校验。"""

    def test_fixed_radius_initialization(self):
        """测试固定半径初始化后会直接保存半径值。"""
        plugin = BaseNeighbourhoodProcessing(1000.0)
        data = np.ones((3, 3), dtype=np.float32)
        returned = plugin.process(data)
        assert returned is data
        assert plugin.radius == 1000.0

    def test_radii_lead_times_mismatch_raises(self):
        """测试 radii 与 lead_times 长度不一致时会报错。"""
        with pytest.raises(ValueError, match="长度不一致"):
            BaseNeighbourhoodProcessing([1000.0, 2000.0], lead_times=[1.0])

    def test_reads_lead_times_from_xarray(self):
        """测试 xarray 输入可自动读取时效并完成半径插值。"""
        plugin = BaseNeighbourhoodProcessing([1000.0, 3000.0], lead_times=[1.0, 3.0])
        data = make_dataarray(np.ones((2, 3, 3), dtype=np.float32), dtime_values=[1.0, 2.0])
        plugin.process(data)
        np.testing.assert_allclose(plugin.radius, np.array([1000.0, 2000.0]))

    def test_numpy_requires_lead_times_for_variable_radius(self):
        """测试 numpy 输入在可变半径场景下必须显式提供 input_lead_times。"""
        plugin = BaseNeighbourhoodProcessing([1000.0, 3000.0], lead_times=[1.0, 3.0])
        with pytest.raises(ValueError, match="input_lead_times"):
            plugin.process(np.ones((2, 3, 3), dtype=np.float32))

    def test_detects_unmasked_nan(self):
        """测试未掩码 NaN 会在基类检查阶段被拦截。"""
        plugin = BaseNeighbourhoodProcessing(1000.0)
        data = np.array([[1.0, np.nan], [1.0, 1.0]], dtype=np.float32)
        with pytest.raises(ValueError, match="NaN"):
            plugin.process(data)

    def test_dataarray_rejects_nan(self):
        """测试 DataArray 输入在基类阶段拦截裸 NaN。"""
        plugin = BaseNeighbourhoodProcessing(1000.0)
        values = np.array([[1.0, np.nan], [1.0, 1.0]], dtype=np.float32)
        data = make_dataarray(values)
        with pytest.raises(ValueError, match="NaN"):
            plugin.process(data)

    def test_masked_array_rejects_unmasked_nan(self):
        """测试 MaskedArray 在掩码外含 NaN 时仍会报错。"""
        plugin = BaseNeighbourhoodProcessing(1000.0)
        data = np.ma.array(
            [[1.0, np.nan], [1.0, 1.0]],
            mask=[[False, False], [False, False]],
            dtype=np.float32,
        )
        with pytest.raises(ValueError, match="NaN"):
            plugin.process(data)


class TestUtilityFunctions:
    """测试工具函数：半径校验、核生成。"""

    def test_check_radius_against_distance_passes(self):
        """测试合法邻域半径可以通过空间域大小检查。"""
        check_radius_against_distance(1.0, shape=(3, 3), grid_spacing=1.0)

    def test_check_radius_against_distance_raises(self):
        """测试超出空间域允许范围的邻域半径会报错。"""
        with pytest.raises(ValueError, match="超过空间域允许的最大距离"):
            check_radius_against_distance(10.0, shape=(3, 3), grid_spacing=1.0)

    def test_circular_kernel_binary_mode(self):
        """测试圆形核在常权模式下正确生成。"""
        binary = circular_kernel(1, weighted_mode=False)
        assert binary.shape == (3, 3)
        assert set(np.unique(binary)).issubset({0.0, 1.0})

    def test_circular_kernel_weighted_mode(self):
        """测试圆形核在加权模式下中心权重高于边缘。"""
        weighted = circular_kernel(1, weighted_mode=True)
        assert weighted.shape == (3, 3)
        assert weighted[1, 1] > weighted[0, 1]


class TestNeighbourhoodProcessingCore:
    """测试邻域处理核心功能：方形/圆形邻域、求和/平均、掩码处理。"""

    def test_square_sum_numpy(self):
        """测试方形邻域求和在 numpy 输入下的基础结果。"""
        plugin = NeighbourhoodProcessing("square", radii=1.0, sum_only=True, re_mask=False)
        data = np.ones((3, 3), dtype=np.float32)
        result = plugin.process(data, grid_spacing=1.0)
        expected = np.array(
            [[4.0, 6.0, 4.0], [6.0, 9.0, 6.0], [4.0, 6.0, 4.0]],
            dtype=np.float32,
        )
        np.testing.assert_allclose(result, expected)

    def test_external_mask_and_remask(self):
        """测试外部掩码与 re_mask=True 时的输出掩码行为。"""
        plugin = NeighbourhoodProcessing("square", radii=1.0, sum_only=False, re_mask=True)
        data = np.ones((3, 3), dtype=np.float32)
        mask = np.ones((3, 3), dtype=np.int32)
        mask[1, 1] = 0
        result = plugin.process(data, mask=mask, grid_spacing=1.0)
        assert np.ma.isMaskedArray(result)
        assert result.mask[1, 1]

    def test_xarray_matches_numpy(self):
        """测试等价输入下 xarray 与 numpy 结果一致。"""
        data = np.arange(9, dtype=np.float32).reshape(3, 3)
        plugin = NeighbourhoodProcessing("square", radii=1.0, sum_only=False, re_mask=False)
        result_np = plugin.process(data, grid_spacing=1.0)
        result_xr = plugin.process(make_dataarray(data))
        np.testing.assert_allclose(result_np, np.asarray(result_xr)[0, 0, 0, 0, :, :])

    def test_complex_input_support(self):
        """测试邻域处理支持复数输入。"""
        plugin = NeighbourhoodProcessing("square", radii=1.0, sum_only=False, re_mask=False)
        data = np.array(
            [
                [1.0 + 1.0j, 1.0 + 0.0j, 0.0 + 1.0j],
                [1.0 + 2.0j, 2.0 + 1.0j, 1.0 + 0.0j],
                [0.0 + 1.0j, 1.0 + 1.0j, 2.0 + 0.0j],
            ],
            dtype=np.complex64,
        )
        result = plugin.process(data, grid_spacing=1.0)
        assert np.iscomplexobj(result)
        assert result.shape == data.shape
        assert result.dtype == np.complex64

    def test_multilead_slices_with_variable_radius(self):
        """测试多切片输入会按各自时效使用对应邻域半径。"""
        plugin = NeighbourhoodProcessing(
            "square", radii=[1.0, 2.0], lead_times=[1.0, 2.0], sum_only=True, re_mask=False
        )
        data = np.ones((2, 5, 5), dtype=np.float32)
        result = plugin.process(
            data, grid_spacing=1.0, input_lead_times=np.array([1.0, 2.0])
        )
        assert result.shape == (2, 5, 5)
        np.testing.assert_allclose(result[0, 2, 2], 9.0)   # 半径1: 3x3=9
        np.testing.assert_allclose(result[1, 2, 2], 25.0)  # 半径2: 5x5=25

    def test_weighted_mode_with_square_raises(self):
        """测试 weighted_mode 不能与 square 邻域组合使用。"""
        with pytest.raises(ValueError, match="weighted_mode"):
            NeighbourhoodProcessing("square", radii=1.0, weighted_mode=True)


class TestGeneratePercentilesFromANeighbourhood:
    """测试百分位邻域处理功能。"""

    def test_single_percentile_keeps_axis(self):
        """测试单一百分位请求时仍保留 percentile 轴。"""
        plugin = GeneratePercentilesFromANeighbourhood(radii=1.0, percentiles=[10.0])
        data = np.ones((2, 3, 3), dtype=np.float32)
        result = plugin.process(data, grid_spacing=1.0)
        assert result.shape == (1, 2, 3, 3)

    def test_percentile_order_preserved(self):
        """测试百分位顺序与输入顺序保持一致。"""
        data = np.arange(9, dtype=np.float32).reshape(3, 3)
        plugin = GeneratePercentilesFromANeighbourhood(radii=1.0, percentiles=[90.0, 10.0])
        result = plugin.process(data, grid_spacing=1.0)
        assert result.shape[0] == 2

    def test_xarray_numpy_equivalence(self):
        """测试 xarray 与 numpy 输入结果一致。"""
        data = np.arange(9, dtype=np.float32).reshape(3, 3)
        plugin = GeneratePercentilesFromANeighbourhood(radii=1.0, percentiles=[90.0, 10.0])
        result_np = plugin.process(data, grid_spacing=1.0)
        result_xr = plugin.process(make_dataarray(data))
        actual = np.asarray(result_xr)[0, :, 0, 0, :, :]
        np.testing.assert_allclose(actual, result_np)

    def test_xarray_percentile_on_level_dimension(self):
        """六维输出：member 保持集合维，level 为邻域百分位坐标。"""
        data = make_dataarray(np.arange(9, dtype=np.float32).reshape(3, 3))
        plugin = GeneratePercentilesFromANeighbourhood(
            radii=1.0, percentiles=[25.0, 75.0]
        )
        result = plugin.process(data)
        assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
        assert result.sizes["member"] == 1
        assert result.sizes["level"] == 2
        np.testing.assert_allclose(
            result.coords["level"].values, np.array([25.0, 75.0], dtype=np.float32)
        )
        assert result.attrs.get("level_type") == "neighbourhood_percentile"
        assert result.attrs.get("level_units") == "%"

    def test_expected_2d_values(self):
        """测试二维样例在圆形邻域下得到预期的百分位结果。"""
        plugin = GeneratePercentilesFromANeighbourhood(radii=1.0, percentiles=[50.0])
        data = np.array(
            [
                [1.0, 1.0, 1.0],
                [1.0, 0.0, 1.0],
                [1.0, 1.0, 1.0],
            ],
            dtype=np.float32,
        )
        result = plugin.process(data, grid_spacing=1.0)
        np.testing.assert_allclose(result[0], np.ones((3, 3), dtype=np.float32))

    def test_reject_masked_input(self):
        """测试邻域百分位当前仍拒绝 masked 输入。"""
        plugin = GeneratePercentilesFromANeighbourhood(radii=1.0, percentiles=[50.0])
        data = np.ma.masked_array(
            np.ones((3, 3), dtype=np.float32),
            mask=np.zeros((3, 3), dtype=bool),
        )
        with pytest.raises(NotImplementedError):
            plugin.process(data, grid_spacing=1.0)


class TestGeographicRegridPath:
    """测试经纬输入的投影重网格适配路径。"""

    def test_geographic_input_returns_original_degree_coordinates(self):
        """经纬输入应经投影计算后回到原始经纬坐标。"""
        data = make_geographic_dataarray(np.ones((7, 7), dtype=np.float32))
        plugin = NeighbourhoodProcessing(
            "square", radii=2000.0, sum_only=True, re_mask=False
        )
        result = plugin.process(data)
        assert isinstance(result, xr.DataArray)
        assert result.dims == data.dims
        assert "degree" in result.coords["lat"].attrs["units"].lower()
        assert "degree" in result.coords["lon"].attrs["units"].lower()
        np.testing.assert_array_equal(result.coords["lat"].values, data.coords["lat"].values)
        np.testing.assert_array_equal(result.coords["lon"].values, data.coords["lon"].values)

    def test_geographic_input_without_units(self):
        """无 units 的经纬坐标应默认走经纬适配分支。"""
        data = make_geographic_dataarray(np.ones((7, 7), dtype=np.float32), with_units=False)
        plugin = NeighbourhoodProcessing(
            "square", radii=2000.0, sum_only=True, re_mask=False
        )
        result = plugin.process(data)
        assert "units" not in result.coords["lat"].attrs
        assert "units" not in result.coords["lon"].attrs
        np.testing.assert_array_equal(result.coords["lat"].values, data.coords["lat"].values)

    def test_projected_input_skips_geographic_regrid(self):
        """投影米制输入（距离单位）不应触发经纬适配。"""
        data = make_dataarray(np.ones((5, 5), dtype=np.float32))
        from neighbourhood_probability_processing.src.utils._regrid import (
            is_geographic_spatial_dataarray,
            is_projected_spatial_dataarray,
        )

        assert is_projected_spatial_dataarray(data)
        assert not is_geographic_spatial_dataarray(data)

    def test_geographic_full_path_matches_adapted_laea_projected_path(self):
        """经纬完整路径 ≡ 同一场挂在适配 LAEA 米轴上的投影路径（数值自洽）。"""
        from neighbourhood_probability_processing.src.utils._regrid import (
            is_projected_spatial_dataarray,
            prepare_geographic_input,
        )

        values = np.arange(7 * 7, dtype=np.float32).reshape(7, 7)
        data = make_geographic_dataarray(values)
        plugin = NeighbourhoodProcessing("square", radii=2000.0, re_mask=False)

        result_geo = plugin.process(data)
        projected, _, ctx = prepare_geographic_input(data)
        assert ctx is not None
        assert is_projected_spatial_dataarray(projected)
        result_on_laea = plugin.process(projected)

        np.testing.assert_allclose(
            np.asarray(result_geo.values, dtype=np.float64),
            np.asarray(result_on_laea.values, dtype=np.float64),
            equal_nan=True,
            atol=0.0,
            rtol=0.0,
        )
        np.testing.assert_array_equal(result_geo.coords["lat"].values, data.coords["lat"].values)
        np.testing.assert_array_equal(result_geo.coords["lon"].values, data.coords["lon"].values)

    def test_geographic_with_mask_matches_adapted_laea_path(self):
        """带外部掩码时，经纬完整路径仍与适配米轴投影路径数值一致。"""
        from neighbourhood_probability_processing.src.utils._regrid import prepare_geographic_input

        values = np.arange(7 * 7, dtype=np.float32).reshape(7, 7)
        data = make_geographic_dataarray(values)
        mask_2d = np.ones((7, 7), dtype=np.float32)
        mask_2d[:2, :] = 0.0
        mask = make_geographic_dataarray(mask_2d)
        plugin = NeighbourhoodProcessing("square", radii=2000.0, re_mask=True)

        result_geo = plugin.process(data, mask=mask)
        projected, projected_mask, ctx = prepare_geographic_input(data, mask)
        assert ctx is not None
        result_on_laea = plugin.process(projected, mask=projected_mask)

        np.testing.assert_allclose(
            np.asarray(result_geo.values, dtype=np.float64),
            np.asarray(result_on_laea.values, dtype=np.float64),
            equal_nan=True,
            atol=0.0,
            rtol=0.0,
        )

    def test_percentile_geographic_matches_adapted_laea_path(self):
        """百分位插件：经纬完整路径 ≡ 适配 LAEA 米轴投影路径。"""
        from neighbourhood_probability_processing.src.utils._regrid import prepare_geographic_input

        values = np.arange(7 * 7, dtype=np.float32).reshape(7, 7)
        data = make_geographic_dataarray(values)
        plugin = GeneratePercentilesFromANeighbourhood(2000.0, percentiles=[50.0])

        result_geo = plugin.process(data)
        projected, _, ctx = prepare_geographic_input(data)
        assert ctx is not None
        result_on_laea = plugin.process(projected)

        np.testing.assert_allclose(
            np.asarray(result_geo.values, dtype=np.float64),
            np.asarray(result_on_laea.values, dtype=np.float64),
            equal_nan=True,
            atol=0.0,
            rtol=0.0,
        )

    def test_adapted_laea_spacing_yields_expected_grid_cells(self):
        """适配后米制格距应对半径给出可预期的格点数。"""
        from neighbourhood_probability_processing.src.utils._grid import _distance_to_number_of_grid_cells
        from neighbourhood_probability_processing.src.utils._regrid import build_geographic_regrid_context

        data = make_geographic_dataarray(np.ones((7, 7), dtype=np.float32))
        ctx = build_geographic_regrid_context(data)
        spacing = float(np.mean(np.abs(np.diff(ctx.projected_lat))))
        assert spacing > 0.0
        # 0.01° 在约 30°N 量级为千米级；半径取 2*spacing 应得到至少 2 格
        radius = 2.0 * spacing
        cells = _distance_to_number_of_grid_cells(radius, spacing)
        assert cells == 2


@_requires_official_data
class TestOfficialBasicNeighbourhood:
    """测试官方基础邻域样例（方形/圆形）。"""

    def test_square_neighbourhood_matches_kgo_and_original(self):
        """测试官方方形基础邻域样例与 KGO 和原算法结果一致。"""
        basic_dir = RESOURCE_ROOT / "basic"
        input_data = load_primary_dataarray(CLI_INPUT_ROOT / "basic" / "input.nc")

        square_result = NeighbourhoodProcessing("square", radii=20000.0).process(input_data)
        square_kgo = clean_fill_values(load_primary_dataarray(basic_dir / "kgo_square.nc"))
        square_original = clean_fill_values(load_primary_dataarray(basic_dir / "original_square.nc"))

        actual, expected = align_result_to_reference(square_result, square_kgo)
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1.0e-6)
        actual, expected = align_result_to_reference(square_result, square_original)
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1.0e-6)

    def test_circular_neighbourhood_matches_original(self):
        """测试官方圆形基础邻域样例与原算法结果一致。

        说明：当前 kgo_circular.nc 与原算法输出并不一致，因此这里只对原算法
        结果做强校验，避免把测试数据自身的差异误判为迁移版算法问题。
        """
        basic_dir = RESOURCE_ROOT / "basic"
        input_data = load_primary_dataarray(CLI_INPUT_ROOT / "basic" / "input.nc")

        circular_result = NeighbourhoodProcessing("circular", radii=20000.0).process(input_data)
        circular_original = clean_fill_values(load_primary_dataarray(basic_dir / "original_circular.nc"))

        actual, expected = align_result_to_reference(circular_result, circular_original)
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1.0e-6)


@_requires_official_data
class TestOfficialMaskedNeighbourhood:
    """测试官方掩码邻域样例（内部掩码/外部掩码）。"""

    def test_internal_masked_matches_kgo_and_original(self):
        """测试官方内部掩码样例与参考结果一致（MaskedArray 路径）。"""
        mask_dir = RESOURCE_ROOT / "mask"
        internal_input = load_primary_dataarray(mask_dir / "input_masked.nc")
        internal_masked = mask_fill_values(internal_input)
        internal_result = NeighbourhoodProcessing("square", radii=20000.0).process(
            internal_masked, grid_spacing=2000.0
        )

        internal_kgo = clean_fill_values(load_primary_dataarray(mask_dir / "kgo_masked.nc"))
        internal_original = clean_fill_values(load_primary_dataarray(mask_dir / "original_masked.nc"))

        valid = ~np.ma.getmaskarray(internal_result)
        assert_allclose_at_valid(internal_result, internal_kgo, valid=valid)
        assert_allclose_at_valid(internal_result, internal_original, valid=valid)
        assert np.ma.isMaskedArray(internal_result)
        masked_data = np.ma.getdata(internal_result)[np.ma.getmaskarray(internal_result)]
        assert not np.all(np.isnan(masked_data))

    def test_dataarray_with_nan_rejects_at_validation(self):
        """测试六维 DataArray 含裸 NaN 时在基类校验阶段报错。"""
        internal_input = load_primary_dataarray(CLI_INPUT_ROOT / "mask" / "input.nc")
        values = np.asarray(internal_input.values, dtype=np.float32).copy()
        values[0, 0, 0, 0, 0, 0] = np.nan
        internal_input = internal_input.copy(deep=True)
        internal_input.values = values
        with pytest.raises(ValueError, match="NaN"):
            NeighbourhoodProcessing("square", radii=20000.0).process(internal_input)

    def test_masked_array_and_external_mask_merge(self):
        """测试 MaskedArray 与外部 mask 按并集合并（对齐原 IMPROVER）。"""
        plugin = NeighbourhoodProcessing("square", radii=1.0, sum_only=False, re_mask=True)
        data = np.ma.ones((3, 3), dtype=np.float32)
        data[0, 0] = np.ma.masked
        mask = np.ones((3, 3), dtype=np.int32)
        mask[2, 2] = 0
        result = plugin.process(data, mask=mask, grid_spacing=1.0)
        assert np.ma.isMaskedArray(result)
        assert result.mask[0, 0]
        assert result.mask[2, 2]
        assert not result.mask[1, 1]

    def test_external_masked_matches_kgo_and_original(self):
        """测试官方外部掩码样例与参考结果一致。"""
        mask_dir = RESOURCE_ROOT / "mask"
        external_input = load_primary_dataarray(CLI_INPUT_ROOT / "mask" / "input.nc")
        external_mask = load_primary_dataarray(CLI_INPUT_ROOT / "mask" / "mask.nc")
        external_result = NeighbourhoodProcessing("square", radii=20000.0).process(
            external_input, mask=external_mask
        )

        external_kgo = clean_fill_values(load_primary_dataarray(mask_dir / "kgo_external_masked.nc"))
        external_original = clean_fill_values(load_primary_dataarray(mask_dir / "original_external_masked.nc"))

        valid = valid_mask_from_external(spatial_array_from_six_dim(external_mask))
        assert_allclose_at_valid(external_result, external_kgo, valid=valid)
        assert_allclose_at_valid(external_result, external_original, valid=valid)
        result_arr, _ = align_result_to_reference(external_result, external_kgo)
        valid = np.broadcast_to(valid, result_arr.shape)
        masked_vals = result_arr[~valid]
        # DataArray + re_mask 路径无效格点写 NaN（兼容 meteva 写盘），不再使用专用大填充值。
        assert masked_vals.size > 0
        assert np.isnan(masked_vals).all()
        assert "missing_value" not in external_result.attrs

    def test_external_masked_remask_false_keeps_neighbourhood_values(self):
        """DataArray 路径 re_mask=False 时无效格点保留邻域统计值。"""
        mask_dir = RESOURCE_ROOT / "mask"
        external_input = load_primary_dataarray(CLI_INPUT_ROOT / "mask" / "input.nc")
        external_mask = load_primary_dataarray(CLI_INPUT_ROOT / "mask" / "mask.nc")
        external_result = NeighbourhoodProcessing(
            "square", radii=20000.0, re_mask=False
        ).process(external_input, mask=external_mask)

        result_arr, _ = align_result_to_reference(
            external_result,
            clean_fill_values(load_primary_dataarray(mask_dir / "kgo_external_masked.nc")),
        )
        mask_arr = spatial_array_from_six_dim(external_mask)
        mask_arr = np.broadcast_to(mask_arr, result_arr.shape)
        masked_vals = result_arr[mask_arr == 0]
        assert masked_vals.size > 0
        # re_mask=False 时无效格点保留邻域统计结果：绝大多数为有限值，
        # 仅邻域完全无有效点处才因除零产生 NaN，因此不应像 re_mask=True 那样全为 NaN。
        assert not np.isnan(masked_vals).all()
        assert np.isfinite(masked_vals).any()
        assert "missing_value" not in external_result.attrs


@_requires_official_data
class TestOfficialPercentileNeighbourhood:
    """测试官方百分位邻域样例。"""

    def test_circular_percentile_matches_kgo_and_original(self):
        """测试官方百分位邻域样例与 KGO 和原算法结果一致。"""
        percentile_dir = RESOURCE_ROOT / "percentile"
        input_data = load_primary_dataarray(
            CLI_INPUT_ROOT / "percentile" / "input_circular_percentile.nc"
        )

        result = GeneratePercentilesFromANeighbourhood(
            radii=20000.0,
            percentiles=[25.0, 50.0, 75.0],
        ).process(input_data)

        kgo = clean_fill_values(load_primary_dataarray(percentile_dir / "kgo_circular_percentile.nc"))
        original = clean_fill_values(load_primary_dataarray(percentile_dir / "original_circular_percentile.nc"))
        actual, expected = align_result_to_reference(result, kgo)
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1.0e-6)
        actual, expected = align_result_to_reference(result, original)
        np.testing.assert_allclose(actual, expected, equal_nan=True, atol=1.0e-6)
