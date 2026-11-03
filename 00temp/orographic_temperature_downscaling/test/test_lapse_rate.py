#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.

"""
层结递减率模块的单元测试。
"""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from orographic_temperature_downscaling.src.lapse_rate import (
    compute_lapse_rate_adjustment,
    ApplyGriddedLapseRate,
    LapseRate,
    DALR,
    ELR
)


def create_test_grid_data(shape, units, data_value):
    """辅助函数，用于创建测试网格数据。"""
    # Create data with the exact shape required first
    data = np.full(shape, data_value, dtype=np.float32)

    # Create grid that matches the data dimensions
    # Extract dimensions from shape: (member, level, time, dtime, lat, lon)
    nmember = shape[0]
    nlevel = shape[1]
    ntime = shape[2]
    ndtime = shape[3]
    nlat = shape[4]
    nlon = shape[5]

    # Create appropriate coordinate lists
    members = [f"m{i}" for i in range(nmember)]
    levels = list(range(nlevel))
    times = [pd.Timestamp("2023-01-01")] * ntime  # Use pandas timestamp
    dtimes = list(range(ndtime))

    # Create longitude and latitude arrays
    lons = np.linspace(0, 10, nlon)
    lats = np.linspace(0, 10, nlat)

    # Create the grid_data directly with xarray to avoid reshape issues
    grd = xr.DataArray(
        data,
        coords={
            'member': members,
            'level': levels,
            'time': times,
            'dtime': dtimes,
            'lat': lats,
            'lon': lons
        },
        dims=['member', 'level', 'time', 'dtime', 'lat', 'lon']
    )
    grd.attrs["units"] = units
    return grd


def create_test_numpy_data(shape, data_value):
    """辅助函数，用于创建测试 numpy 数组数据。"""
    return np.full(shape, data_value, dtype=np.float32)


class TestComputeLapseRateAdjustment:
    """测试 compute_lapse_rate_adjustment 函数"""

    def test_basic_functionality(self):
        """测试基本功能"""
        lapse_rate = np.array([0.01], dtype=np.float32)  # 0.01 K/m
        orog_diff = np.array([100.0], dtype=np.float32)  # 100m

        result = compute_lapse_rate_adjustment(lapse_rate, orog_diff, max_orog_diff_limit=50.0)

        # 前50m使用lapse_rate，后50m使用ELR
        expected = 50.0 * 0.01 + 50.0 * ELR
        assert np.isclose(result[0], expected, atol=1e-6)

    def test_within_limit(self):
        """测试在限制范围内的调整"""
        lapse_rate = np.array([0.01], dtype=np.float32)
        orog_diff = np.array([30.0], dtype=np.float32)  # 小于50m限制

        result = compute_lapse_rate_adjustment(lapse_rate, orog_diff, max_orog_diff_limit=50.0)
        expected = 30.0 * 0.01
        assert np.isclose(result[0], expected, atol=1e-6)

    def test_negative_orog_diff(self):
        """测试负的地形高度差"""
        lapse_rate = np.array([0.01], dtype=np.float32)
        orog_diff = np.array([-100.0], dtype=np.float32)  # -100m

        result = compute_lapse_rate_adjustment(lapse_rate, orog_diff, max_orog_diff_limit=50.0)

        # 前-50m使用lapse_rate，后-50m使用ELR
        expected = -50.0 * 0.01 + (-50.0) * ELR
        assert np.isclose(result[0], expected, atol=1e-6)

    def test_zero_lapse_rate(self):
        """测试零层结递减率"""
        lapse_rate = np.array([0.0], dtype=np.float32)
        orog_diff = np.array([100.0], dtype=np.float32)

        result = compute_lapse_rate_adjustment(lapse_rate, orog_diff, max_orog_diff_limit=50.0)
        expected = 50.0 * ELR  # 只有超出部分使用ELR
        assert np.isclose(result[0], expected, atol=1e-6)


class TestApplyGriddedLapseRate:
    """测试 ApplyGriddedLapseRate 类"""

    @pytest.fixture
    def lapse_rate_plugin(self):
        """创建 ApplyGriddedLapseRate 实例的 fixture"""
        return ApplyGriddedLapseRate()

    def test_xarray_input(self, lapse_rate_plugin):
        """测试 xarray.DataArray 输入"""
        shape = (1, 1, 1, 1, 2, 3)

        # 创建测试数据（支持不同单位）
        temperature = create_test_grid_data(shape, "K", 280.0)
        lapse_rate = create_test_grid_data(shape, "K m-1", 0.01)
        source_orog = create_test_grid_data(shape, "m", 100.0)
        dest_orog = create_test_grid_data(shape, "m", 200.0)  # 100m 高度差

        result = lapse_rate_plugin(temperature, lapse_rate, source_orog, dest_orog)

        # 验证结果形状
        assert result.shape == shape
        assert isinstance(result, xr.DataArray)
        assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")

        # 验证计算结果
        # 高度差100m，前50m用lapse_rate，后50m用ELR
        adjustment = 50.0 * 0.01 + 50.0 * ELR
        expected_temp = 280.0 + adjustment
        assert np.allclose(result, expected_temp, atol=1e-6)

    def test_numpy_input(self, lapse_rate_plugin):
        """测试 numpy.ndarray 输入"""
        shape = (1, 1, 1, 1, 2, 3)

        # 创建测试数据（默认单位：K, K/m, m）
        temperature = create_test_numpy_data(shape, 280.0)
        lapse_rate = create_test_numpy_data(shape, 0.01)
        source_orog = create_test_numpy_data(shape, 100.0)
        dest_orog = create_test_numpy_data(shape, 200.0)

        result = lapse_rate_plugin(temperature, lapse_rate, source_orog, dest_orog)

        # 验证结果形状
        assert result.shape == shape
        assert isinstance(result, np.ndarray)

        # 验证计算结果
        adjustment = 50.0 * 0.01 + 50.0 * ELR
        expected_temp = 280.0 + adjustment
        assert np.allclose(result, expected_temp, atol=1e-6)

    def test_celsius_input(self, lapse_rate_plugin):
        """测试摄氏度输入"""
        shape = (1, 1, 1, 1, 2, 3)

        # 创建测试数据（支持不同单位）
        temperature = create_test_grid_data(shape, "degC", 7.0)  # 7°C = 280.15K
        lapse_rate = create_test_grid_data(shape, "K m-1", 0.01)
        source_orog = create_test_grid_data(shape, "m", 100.0)
        dest_orog = create_test_grid_data(shape, "m", 200.0)

        result = lapse_rate_plugin(temperature, lapse_rate, source_orog, dest_orog)

        # 输出固定为开尔文（与上游 Improver 一致）
        adjustment = 50.0 * 0.01 + 50.0 * ELR
        expected_temp_k = 280.15 + adjustment
        assert np.allclose(result, expected_temp_k, atol=1e-6)
        assert result.attrs.get("units") == "K"

    def test_coordinate_mismatch_error(self, lapse_rate_plugin):
        """测试坐标不匹配错误"""
        shape1 = (1, 1, 1, 1, 2, 3)
        shape2 = (1, 1, 1, 1, 2, 3)  # Same shape but different coordinates

        # 创建测试数据（支持不同单位）
        temperature = create_test_grid_data(shape1, "K", 280.0)
        lapse_rate = create_test_grid_data(shape2, "K m-1", 0.01)
        # 修改 longitude coordinates to be different
        lapse_rate = lapse_rate.assign_coords(lon=np.linspace(5, 15, 3))
        source_orog = create_test_grid_data(shape1, "m", 100.0)
        dest_orog = create_test_grid_data(shape1, "m", 200.0)

        with pytest.raises(ValueError, match="层结递减率与温度场的空间/时效坐标不一致"):
            lapse_rate_plugin(temperature, lapse_rate, source_orog, dest_orog)


class TestLapseRate:
    """测试 LapseRate 类"""

    def test_initialization(self):
        """测试初始化"""
        plugin = LapseRate(max_height_diff=40.0, nbhood_radius=5)

        assert plugin.max_height_diff == 40.0
        assert plugin.nbhood_radius == 5
        assert plugin.nbhood_size == 11  # 2*5 + 1
        assert plugin.ind_central_point == 5

    def test_invalid_parameters(self):
        """测试无效参数"""
        # 最大层结递减率小于最小层结递减率
        with pytest.raises(ValueError, match="最大层结递减率小于最小层结递减率"):
            LapseRate(max_lapse_rate=-0.02, min_lapse_rate=-0.01)

        # 负的邻域半径
        with pytest.raises(ValueError, match="邻域半径小于零"):
            LapseRate(nbhood_radius=-1)

        # 负的最大高度差
        with pytest.raises(ValueError, match="最大高度差小于零"):
            LapseRate(max_height_diff=-10.0)

    def test_basic_lapse_rate_calculation(self):
        """测试基本层结递减率计算"""
        plugin = LapseRate()

        # 创建简单的2D测试数据
        shape_2d = (3, 3)
        temperature_2d = np.full(shape_2d, 280.0, dtype=np.float32)
        orography_2d = np.array([[100, 150, 200],
                                [120, 170, 220],
                                [140, 190, 240]], dtype=np.float32)
        land_mask_2d = np.ones(shape_2d, dtype=bool)  # 全部为陆地

        # 添加一些温度梯度
        temperature_2d[0, :] = 281.0  # 较高温度
        temperature_2d[2, :] = 279.0  # 较低温度

        result = plugin._generate_lapse_rate_array(temperature_2d, orography_2d, land_mask_2d)

        assert result.shape == shape_2d
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32

        # 结果应该在DALR和max_lapse_rate之间
        assert np.all(result >= DALR)
        assert np.all(result <= -3 * DALR)

    def test_land_sea_masking(self):
        """测试陆地-海洋掩膜"""
        plugin = LapseRate()

        shape_2d = (2, 2)
        temperature_2d = np.full(shape_2d, 280.0, dtype=np.float32)
        orography_2d = np.full(shape_2d, 100.0, dtype=np.float32)
        land_mask_2d = np.array([[True, False],  # 陆地, 海洋
                                [True, True]], dtype=bool)  # 陆地, 陆地

        result = plugin._generate_lapse_rate_array(temperature_2d, orography_2d, land_mask_2d)

        # 海洋点应该被设置为DALR
        assert np.isclose(result[0, 1], DALR, atol=1e-6)
        # 陆地点应该有计算值（可能接近DALR但不完全相等）
        # 由于测试数据是均匀的，陆地点也可能返回DALR，所以放宽断言
        assert result[0, 0] >= DALR

    def test_xarray_input_integration(self):
        """测试 xarray.DataArray 输入集成"""
        plugin = LapseRate()

        # 创建测试数据（支持不同单位）
        shape = (1, 1, 1, 1, 3, 3)
        temperature = create_test_grid_data(shape, "K", 280.0)
        orography = create_test_grid_data(shape, "m", 100.0)
        land_sea_mask = create_test_grid_data(shape, "1", 1.0)  # 全部为陆地

        result = plugin(temperature, orography, land_sea_mask)

        assert result.shape == shape
        assert isinstance(result, xr.DataArray)
        assert result.dims == ("member", "level", "time", "dtime", "lat", "lon")
        assert result.dtype == np.float32

        # 所有值应该在有效范围内
        assert np.all(result >= DALR)
        assert np.all(result <= -3 * DALR)

    def test_numpy_input_integration(self):
        """测试 numpy.ndarray 输入集成"""
        plugin = LapseRate()

        # 创建测试数据（支持不同单位）
        shape = (1, 1, 1, 1, 3, 3)
        temperature = create_test_numpy_data(shape, 280.0)  # 默认K
        orography = create_test_numpy_data(shape, 100.0)   # 默认m
        land_sea_mask = create_test_numpy_data(shape, 1.0).astype(bool)  # 全部为陆地

        result = plugin(temperature, orography, land_sea_mask)

        assert result.shape == shape
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32

        # 所有值应该在有效范围内
        assert np.all(result >= DALR)
        assert np.all(result <= -3 * DALR)

    def test_sliding_window_view_correctness(self):
        """测试 sliding_window_view 的正确性"""
        from orographic_temperature_downscaling.src.lapse_rate import LapseRate

        data = np.array([[10, 20, 30],
                         [40, 50, 60],
                         [70, 80, 90]], dtype=np.float32)

        nbhood_radius = 1
        nbhood_size = 3

        # 使用 sliding_window_view
        padded_data = np.pad(data, nbhood_radius, mode='constant', constant_values=np.nan)
        actual_windows = LapseRate()._rolling_window(padded_data, (nbhood_size, nbhood_size))

        # 验证每个窗口的中心值是否正确
        for i in range(3):
            for j in range(3):
                center_value = actual_windows[i, j][1, 1]
                original_value = data[i, j]
                assert np.isclose(center_value, original_value), f"位置 ({i},{j}) 中心值 {center_value} != 原值 {original_value}"

        # 验证窗口形状
        expected_shape = (3, 3, 3, 3)  # (height, width, window_height, window_width)
        assert actual_windows.shape == expected_shape, f"窗口形状错误: {actual_windows.shape} != {expected_shape}"
