#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""迁移版 QPE 函数测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_qpe_retrieval.src.qpe import (
    ZtoR,
    est_rain_rate_a,
    est_rain_rate_hydro,
    est_rain_rate_kdp,
    est_rain_rate_z,
    est_rain_rate_za,
    est_rain_rate_zkdp,
    est_rain_rate_zpoly,
)


def test_est_rain_rate_z_returns_meteva_griddata():
    """迁移后的函数应保持 meteva_base 网格数据结构不变。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    reflectivity = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )

    result = est_rain_rate_z(reflectivity)

    expected = 0.0376 * np.power(np.power(10.0, 0.1 * reflectivity.values), 0.6112)

    assert result.dims == reflectivity.dims
    assert result.shape == reflectivity.shape
    assert result.name == "radar_estimated_rain_rate"
    assert result.attrs["units"] == "mm/h"
    assert result.attrs["long_name"] == "rain rate estimated from reflectivity"
    assert result.attrs["qpe_method"] == "z"
    assert result.attrs["dtime_units"] == "hour"
    assert "time_type" in result.attrs
    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_z_inherits_provenance_not_frequency():
    """降水输出应继承站点溯源属性，但不继承雷达 frequency。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    reflectivity = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )
    reflectivity.attrs["site_code"] = "Z9010"
    reflectivity.attrs["scan_time"] = "2025-07-24 19:24:00"
    reflectivity.attrs["frequency"] = 2.87e9
    reflectivity.attrs["units"] = "dBZ"

    result = est_rain_rate_z(reflectivity)

    assert result.attrs["site_code"] == "Z9010"
    assert result.attrs["scan_time"] == "2025-07-24 19:24:00"
    assert "frequency" not in result.attrs
    assert result.attrs["units"] == "mm/h"
    assert result.attrs["qpe_method"] == "z"
    assert result.attrs["alpha"] == pytest.approx(0.0376)
    assert result.attrs["beta"] == pytest.approx(0.6112)


def test_est_rain_rate_z_accepts_output_name():
    """迁移后的函数应允许自定义输出名称。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    reflectivity = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )

    result = est_rain_rate_z(reflectivity, rr_field="custom_rain_rate")

    assert result.name == "custom_rain_rate"


def test_est_rain_rate_zpoly_returns_expected_values():
    """多项式 Z-R 关系应返回与公式一致的结果。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    reflectivity = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )

    result = est_rain_rate_zpoly(reflectivity)

    refl = reflectivity.values
    refl2 = refl * refl
    refl3 = refl * refl2
    refl4 = refl * refl3
    expected = np.power(
        10.0,
        -2.3 + 0.17 * refl - 5.1e-3 * refl2 + 9.8e-5 * refl3 - 6e-7 * refl4,
    )

    assert result.shape == reflectivity.shape
    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def _make_multi_level_grid(level_values: list[np.ndarray]) -> "meb.grid_data":
    """Build meteva grid with level dim = len(level_values), each (nlat, nlon)."""
    nlevel = len(level_values)
    nlat, nlon = level_values[0].shape
    grid = meb.grid(
        [100, 100 + nlon - 1, 1],
        [30, 30 + nlat - 1, 1],
        level_list=list(range(nlevel)),
    )
    data = np.stack(
        [np.asarray(v, dtype=np.float32) for v in level_values],
        axis=0,
    ).reshape(1, nlevel, 1, 1, nlat, nlon)
    return meb.grid_data(grid, data=data)


def test_est_rain_rate_kdp_multi_level_applies_per_level():
    """多层 level 应对每一仰角格点逐元素计算 KDP-R。"""
    level0 = np.array([[0.5, 1.0], [1.5, 2.0]], dtype=np.float32)
    level1 = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    kdp = _make_multi_level_grid([level0, level1])

    result = est_rain_rate_kdp(kdp)

    assert result.shape == kdp.shape
    expected0 = 29.70 * np.power(level0, 0.8500)
    expected1 = 29.70 * np.power(level1, 0.8500)
    np.testing.assert_allclose(result.values[0, 0, 0, 0, :, :], expected0.astype(np.float32))
    np.testing.assert_allclose(result.values[0, 1, 0, 0, :, :], expected1.astype(np.float32))


def test_est_rain_rate_kdp_uses_default_c_band_coefficients():
    """未指定频率时，KDP 算法应默认使用 C 波段系数。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    kdp = meb.grid_data(
        grid,
        data=np.array([[0.5, -0.2], [1.0, 2.0]], dtype=np.float32),
    )

    result = est_rain_rate_kdp(kdp)

    kdp_expected = kdp.values.copy()
    kdp_expected[kdp_expected < 0] = 0.0
    expected = 29.70 * np.power(kdp_expected, 0.8500)

    assert result.shape == kdp.shape
    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_kdp_reads_frequency_from_attrs():
    """未显式传入频率时，应允许从网格属性中读取频率。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    kdp = meb.grid_data(
        grid,
        data=np.array([[0.5, 1.0], [1.5, 2.0]], dtype=np.float32),
    )
    kdp.attrs["frequency"] = 3.0e9

    result = est_rain_rate_kdp(kdp)

    expected = 50.70 * np.power(kdp.values, 0.8500)

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_kdp_reads_band_from_attrs():
    """未显式传入频率时，应允许从网格属性中读取频段。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    kdp = meb.grid_data(
        grid,
        data=np.array([[0.5, 1.0], [1.5, 2.0]], dtype=np.float32),
    )
    kdp.attrs["frequency"] = 13e9

    result = est_rain_rate_kdp(kdp)

    expected = 15.81 * np.power(kdp.values, 0.7992)

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_a_uses_default_c_band_for_unknown_band():
    """无法识别频段且无频率时，A 算法应默认使用 C 波段系数。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    att = meb.grid_data(
        grid,
        data=np.array([[0.01, 0.05], [0.10, 0.20]], dtype=np.float32),
    )
    att.attrs["band"] = "unknown"

    result = est_rain_rate_a(att)

    expected = 250.0 * np.power(att.values, 0.91)

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_a_uses_default_c_band_coefficients():
    """未指定频率时，A 算法应默认使用 C 波段系数。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    att = meb.grid_data(
        grid,
        data=np.array([[0.01, 0.05], [0.10, 0.20]], dtype=np.float32),
    )

    result = est_rain_rate_a(att)

    expected = 250.0 * np.power(att.values, 0.91)

    assert result.shape == att.shape
    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_a_reads_frequency_from_attrs():
    """未显式传入频率时，应允许从网格属性中读取频率。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    att = meb.grid_data(
        grid,
        data=np.array([[0.01, 0.05], [0.10, 0.20]], dtype=np.float32),
    )
    att.attrs["frequency"] = 3.0e9

    result = est_rain_rate_a(att)

    expected = 3100.0 * np.power(att.values, 1.03)

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_zkdp_blends_two_results():
    """ZKDP 算法应按阈值拼接两种降水率结果。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    refl = meb.grid_data(
        grid,
        data=np.array([[20.0, 30.0], [40.0, 50.0]], dtype=np.float32),
    )
    kdp = meb.grid_data(
        grid,
        data=np.array([[0.2, 0.5], [1.0, 2.0]], dtype=np.float32),
    )

    result = est_rain_rate_zkdp(refl, kdp, thresh=10.0, thresh_max=True)

    rain_z = est_rain_rate_z(refl)
    rain_kdp = est_rain_rate_kdp(kdp)
    expected = rain_z.values.copy()
    expected[rain_z.values > 10.0] = rain_kdp.values[rain_z.values > 10.0]

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_za_blends_two_results():
    """ZA 算法应按阈值拼接两种降水率结果。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    refl = meb.grid_data(
        grid,
        data=np.array([[20.0, 30.0], [40.0, 50.0]], dtype=np.float32),
    )
    att = meb.grid_data(
        grid,
        data=np.array([[0.01, 0.05], [0.10, 0.20]], dtype=np.float32),
    )

    result = est_rain_rate_za(att=att, refl=refl, thresh=0.04, thresh_max=False)

    rain_z = est_rain_rate_z(refl)
    rain_a = est_rain_rate_a(att)
    expected = rain_a.values.copy()
    expected[rain_a.values < 0.04] = rain_z.values[rain_a.values < 0.04]

    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_est_rain_rate_hydro_assigns_by_class():
    """HYDRO 算法应按水凝物分类选择不同关系式。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    refl = meb.grid_data(
        grid,
        data=np.array([[20.0, 30.0], [40.0, 50.0]], dtype=np.float32),
    )
    att = meb.grid_data(
        grid,
        data=np.array([[0.01, 0.05], [0.10, 0.20]], dtype=np.float32),
    )
    hydro = meb.grid_data(
        grid,
        data=np.array([[1.0, 3.0], [7.0, 5.0]], dtype=np.float32),
    )

    result = est_rain_rate_hydro(refl, att, hydro, thresh=0.04, thresh_max=False)

    snow_z = est_rain_rate_z(refl, alpha=0.1, beta=0.5)
    rain_z = est_rain_rate_z(refl)
    rain_a = est_rain_rate_a(att)
    blended = rain_a.values.copy()
    blended[rain_a.values < 0.04] = rain_z.values[rain_a.values < 0.04]

    expected = np.full(hydro.values.shape, np.nan, dtype=np.float32)
    expected[hydro.values == 1] = snow_z.values[hydro.values == 1]
    expected[hydro.values == 3] = blended[hydro.values == 3]
    expected[hydro.values == 7] = 0.6 * rain_z.values[hydro.values == 7]
    expected[hydro.values == 5] = blended[hydro.values == 5]

    np.testing.assert_allclose(result.values, expected.astype(np.float32), equal_nan=True)


def test_z_to_r_returns_expected_values():
    """ZtoR 应按经典 Z-R 关系返回降水率。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    refl = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )

    result = ZtoR(
        refl,
        a=300.0,
        b=1.4,
        save_name="custom_prate",
    )

    ref_linear = np.power(10.0, refl.values / 10.0)
    expected = np.power(ref_linear / 300.0, 1.0 / 1.4)

    assert result.name == "custom_prate"
    assert result.attrs["units"] == "mm/h"
    np.testing.assert_allclose(result.values, expected.astype(np.float32))


def test_z_to_r_uses_default_output_name():
    """ZtoR 未指定 save_name 时应使用默认字段名。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1])
    refl = meb.grid_data(
        grid,
        data=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
    )

    result = ZtoR(refl)
    assert result.name == "NWS_primary_prate"


def test_est_rain_rate_z_requires_reflectivity_input():
    """缺少反射率输入时应抛出异常。"""
    with pytest.raises((TypeError, ValueError)):
        est_rain_rate_z(None)
