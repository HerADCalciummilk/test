#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""feels_like_temperature 模块单元测试。"""

from __future__ import annotations

import importlib.util
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from feels_like_temperature.src.feels_like_temperature import (
    CalculateWindChill,
    _calculate_apparent_temperature,
    _feels_like_temperature,
    calculate_feels_like_temperature,
)
from feels_like_temperature.src.utils._feels_like import (
    _calculate_svp_in_air,
    _svp_pure_water_goff_gratch,
)


REQUIRED_DIMS = ("member", "level", "time", "dtime", "lat", "lon")
HAS_METEVA_BASE = importlib.util.find_spec("meteva_base") is not None


def create_meb6d_dataarray(
    value: float,
    units: str,
    *,
    shape: tuple[int, int, int, int, int, int] = (1, 1, 1, 1, 2, 3),
    name: str = "data",
) -> xr.DataArray:
    """构造标准 meteva_base 六维网格 DataArray。"""
    data = np.full(shape, value, dtype=np.float32)
    coords = {
        "member": [f"m{i}" for i in range(shape[0])],
        "level": [float(i) for i in range(shape[1])],
        "time": [pd.Timestamp("2023-01-01 00:00:00")] * shape[2],
        "dtime": list(range(shape[3])),
        "lat": np.linspace(20.0, 21.0, shape[4], dtype=np.float32),
        "lon": np.linspace(100.0, 101.0, shape[5], dtype=np.float32),
    }
    arr = xr.DataArray(data, dims=REQUIRED_DIMS, coords=coords, name=name)
    arr.attrs["units"] = units
    return arr


def create_non_meb_dataarray(
    value: float,
    units: str,
    *,
    shape: tuple[int, int] = (2, 3),
) -> xr.DataArray:
    """构造非 meteva_base 网格（二维投影坐标）DataArray。"""
    data = np.full(shape, value, dtype=np.float32)
    arr = xr.DataArray(
        data,
        dims=("projection_y_coordinate", "projection_x_coordinate"),
        coords={
            "projection_y_coordinate": np.linspace(0.0, 1.0, shape[0], dtype=np.float32),
            "projection_x_coordinate": np.linspace(0.0, 1.0, shape[1], dtype=np.float32),
        },
        name="data",
    )
    arr.attrs["units"] = units
    return arr


class TestFeelsLikeTemperature:
    """体感温度算法测试。"""

    @pytest.fixture
    def wind_chill_plugin(self) -> CalculateWindChill:
        """构造风寒插件实例。"""
        return CalculateWindChill()

    def test_svp_pure_water_goff_gratch(self) -> None:
        """验证 Goff-Gratch 饱和水汽压计算与参考值一致。"""
        test_cases = [
            (250.0, 0.7595),
            (273.15, 6.1064),
            (273.16, 6.1114),
            (293.15, 23.3708),
            (310.0, 62.2475),
        ]
        temperatures = np.array([item[0] for item in test_cases], dtype=np.float32)
        expected = np.array([item[1] for item in test_cases], dtype=np.float32)
        actual = _svp_pure_water_goff_gratch(temperatures)
        np.testing.assert_allclose(actual, expected, rtol=0.005)

    def test_calculate_svp_in_air(self) -> None:
        """验证气压修正后的饱和水汽压应略高于纯水系统值。"""
        temperature = np.array([293.15], dtype=np.float32)
        pressure = np.array([101325.0], dtype=np.float32)
        svp_base = _svp_pure_water_goff_gratch(temperature) * 100.0
        svp_air = _calculate_svp_in_air(temperature, pressure)
        assert svp_air[0] > svp_base[0]
        factor = svp_air[0] / svp_base[0]
        assert 1.004 < factor < 1.006

    def test_calculate_wind_chill_numpy(self, wind_chill_plugin: CalculateWindChill) -> None:
        """验证 numpy 输入的风寒温度计算。"""
        t = np.array([0.0], dtype=np.float32)
        w_ms = np.array([3.0], dtype=np.float32)
        result = wind_chill_plugin(t, w_ms, wind_speed_units="m s-1")
        assert result[0] < t[0]

        t_known = np.array([1.7], dtype=np.float32)
        w_kmh = np.array([10.8], dtype=np.float32)
        expected = np.array([-1.4754], dtype=np.float32)
        actual = wind_chill_plugin._calculate_wind_chill(t_known, w_kmh)
        np.testing.assert_almost_equal(actual, expected, decimal=4)

    def test_calculate_wind_chill_xarray_meb6d(self, wind_chill_plugin: CalculateWindChill) -> None:
        """xarray 标准 meb6d 输入应返回 DataArray。"""
        if not HAS_METEVA_BASE:
            pytest.skip("meteva_base 未安装，跳过 xarray meb6d 严格校验测试。")
        t = create_meb6d_dataarray(2.0, "degC", name="air_temperature")
        w = create_meb6d_dataarray(8.0, "m s-1", name="wind_speed")
        result = wind_chill_plugin(t, w)
        assert isinstance(result, xr.DataArray)
        assert result.dims == REQUIRED_DIMS
        assert result.shape == t.shape
        assert result.attrs.get("units") == "degC"

    def test_calculate_wind_chill_xarray_non_meb6d_raise(
        self, wind_chill_plugin: CalculateWindChill
    ) -> None:
        """xarray 非 meb6d 输入应直接报错。"""
        if not HAS_METEVA_BASE:
            pytest.skip("meteva_base 未安装，跳过 xarray meb6d 严格校验测试。")
        t = create_non_meb_dataarray(2.0, "degC")
        w = create_non_meb_dataarray(8.0, "m s-1")
        with pytest.raises(ValueError, match="griddata dims must be"):
            _ = wind_chill_plugin(t, w)

    def test_feels_like_temperature_fusion(self) -> None:
        """验证体感温度冷区/热区/过渡区融合逻辑。"""
        temp_cold = np.array([5.0], dtype=np.float32)
        apparent_cold = np.array([6.0], dtype=np.float32)
        wind_chill_cold = np.array([2.0], dtype=np.float32)
        out_cold = _feels_like_temperature(temp_cold, apparent_cold, wind_chill_cold)
        assert out_cold[0] == wind_chill_cold[0]

        temp_hot = np.array([25.0], dtype=np.float32)
        apparent_hot = np.array([28.0], dtype=np.float32)
        wind_chill_hot = np.array([22.0], dtype=np.float32)
        out_hot = _feels_like_temperature(temp_hot, apparent_hot, wind_chill_hot)
        assert out_hot[0] == apparent_hot[0]

        temp_mid = np.array([15.0], dtype=np.float32)
        apparent_mid = np.array([18.0], dtype=np.float32)
        wind_chill_mid = np.array([12.0], dtype=np.float32)
        out_mid = _feels_like_temperature(temp_mid, apparent_mid, wind_chill_mid)
        expected_mid = 0.5 * apparent_mid[0] + 0.5 * wind_chill_mid[0]
        assert abs(out_mid[0] - expected_mid) < 0.1

    def test_calculate_feels_like_temperature_numpy(self) -> None:
        """numpy 输入应返回 numpy 输出，且形状一致。"""
        shape = (1, 1, 1, 1, 2, 3)
        t = np.full(shape, 15.0, dtype=np.float32)
        w = np.full(shape, 5.0, dtype=np.float32)
        rh = np.full(shape, 0.5, dtype=np.float32)
        p = np.full(shape, 101325.0, dtype=np.float32)
        out = calculate_feels_like_temperature(t, w, rh, p)
        assert isinstance(out, np.ndarray)
        assert out.shape == shape

    def test_calculate_feels_like_temperature_xarray_meb6d(self) -> None:
        """xarray meb6d 输入应返回 meb6d DataArray。"""
        if not HAS_METEVA_BASE:
            pytest.skip("meteva_base 未安装，跳过 xarray meb6d 严格校验测试。")
        t = create_meb6d_dataarray(15.0, "degC", name="air_temperature")
        w = create_meb6d_dataarray(5.0, "m s-1", name="wind_speed")
        rh = create_meb6d_dataarray(0.5, "1", name="relative_humidity")
        p = create_meb6d_dataarray(101325.0, "Pa", name="air_pressure_at_sea_level")
        out = calculate_feels_like_temperature(t, w, rh, p)
        assert isinstance(out, xr.DataArray)
        assert out.dims == REQUIRED_DIMS
        assert out.shape == t.shape
        assert out.attrs.get("units") == "degC"

    def test_calculate_feels_like_temperature_xarray_non_meb6d_raise(self) -> None:
        """xarray 非 meb6d 输入应直接报错。"""
        if not HAS_METEVA_BASE:
            pytest.skip("meteva_base 未安装，跳过 xarray meb6d 严格校验测试。")
        t = create_non_meb_dataarray(15.0, "degC")
        w = create_non_meb_dataarray(5.0, "m s-1")
        rh = create_non_meb_dataarray(0.5, "1")
        p = create_non_meb_dataarray(101325.0, "Pa")
        with pytest.raises(ValueError, match="griddata dims must be"):
            _ = calculate_feels_like_temperature(t, w, rh, p)

    def test_calculate_feels_like_temperature_units_consistency(self) -> None:
        """验证常见单位写法下结果一致性。"""
        if not HAS_METEVA_BASE:
            pytest.skip("meteva_base 未安装，跳过 xarray meb6d 严格校验测试。")
        t_k = create_meb6d_dataarray(288.15, "K", name="air_temperature")
        t_c = create_meb6d_dataarray(15.0, "degC", name="air_temperature")
        w_ms = create_meb6d_dataarray(5.0, "m s-1", name="wind_speed")
        w_kmh = create_meb6d_dataarray(18.0, "km/h", name="wind_speed")
        rh_1 = create_meb6d_dataarray(0.5, "1", name="relative_humidity")
        rh_pct = create_meb6d_dataarray(50.0, "%", name="relative_humidity")
        p_pa = create_meb6d_dataarray(101325.0, "Pa", name="air_pressure_at_sea_level")
        p_hpa = create_meb6d_dataarray(1013.25, "hPa", name="air_pressure_at_sea_level")

        out_k = calculate_feels_like_temperature(t_k, w_ms, rh_1, p_pa)
        out_c = calculate_feels_like_temperature(t_c, w_ms, rh_1, p_pa)
        out_kmh = calculate_feels_like_temperature(t_k, w_kmh, rh_1, p_pa)
        out_pct = calculate_feels_like_temperature(t_k, w_ms, rh_pct, p_pa)
        out_hpa = calculate_feels_like_temperature(t_k, w_ms, rh_1, p_hpa)

        # K 与 degC 输入仅单位不同，换算后数值应一致。
        np.testing.assert_allclose(
            np.asarray(out_k) - 273.15,
            np.asarray(out_c),
            atol=1e-3,
        )
        np.testing.assert_allclose(np.asarray(out_k), np.asarray(out_kmh), atol=1e-3)
        np.testing.assert_allclose(np.asarray(out_k), np.asarray(out_pct), atol=1e-3)
        np.testing.assert_allclose(np.asarray(out_k), np.asarray(out_hpa), atol=1e-3)
