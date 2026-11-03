#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""基于官方样例数据的 lapse_rate 算法对照测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from orographic_temperature_downscaling.src.lapse_rate import ApplyGriddedLapseRate, LapseRate


ROOT = Path(__file__).resolve().parents[1]
APPLY_DATA_DIR = ROOT / "test_data" / "apply_lapse_rate_data"
LAPSE_DATA_DIR = ROOT / "test_data" / "temp_lapse_rate_data"
APPLY_CLI_INPUT_DIR = APPLY_DATA_DIR / "cli_input"
LAPSE_CLI_INPUT_DIR = LAPSE_DATA_DIR / "cli_input"


def _as_spatial(values: np.ndarray) -> np.ndarray:
    """将六维 meb6d 或二维场统一为二维空间数组以便对照。"""
    arr = np.squeeze(np.asarray(values))
    if arr.ndim != 2:
        raise AssertionError(f"expected 2D spatial values, got shape {arr.shape}")
    return arr


def _assert_files_exist(paths: list[Path]) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"官方测试数据缺失: {missing}")


def test_official_apply_gridded_lapse_rate_with_actual_orog_diff() -> None:
    """验证 ApplyGriddedLapseRate 与官方 KGO、原算法结果一致。"""
    files = {
        "temperature": APPLY_CLI_INPUT_DIR / "ukvx_temperature.nc",
        "lapse_rate": APPLY_CLI_INPUT_DIR / "ukvx_lapse_rate.nc",
        "source_orog": APPLY_CLI_INPUT_DIR / "ukvx_orography.nc",
        "dest_orog": APPLY_CLI_INPUT_DIR / "highres_orog.nc",
        "kgo": APPLY_DATA_DIR / "kgo.nc",
        "original": APPLY_DATA_DIR / "original_algorithm_result.nc",
    }
    _assert_files_exist(list(files.values()))

    temperature = xr.open_dataset(files["temperature"], decode_timedelta=False)["air_temperature"]
    lapse_rate = xr.open_dataset(files["lapse_rate"], decode_timedelta=False)["lapse_rate"]
    source_orog = xr.open_dataset(files["source_orog"], decode_timedelta=False)["surface_altitude"]
    dest_orog = xr.open_dataset(files["dest_orog"], decode_timedelta=False)["surface_altitude"]
    expected = xr.open_dataset(files["kgo"], decode_timedelta=False)["air_temperature"].values
    original = xr.open_dataset(files["original"], decode_timedelta=False)["air_temperature"].values

    result = ApplyGriddedLapseRate()(temperature, lapse_rate, source_orog, dest_orog)
    result_values = _as_spatial(
        result.values if isinstance(result, xr.DataArray) else np.asarray(result)
    )
    expected_values = _as_spatial(expected)
    original_values = _as_spatial(original)

    assert result_values.shape == expected_values.shape
    np.testing.assert_allclose(result_values, expected_values, atol=1e-4, rtol=1e-6)
    np.testing.assert_allclose(result_values, original_values, atol=1e-4, rtol=1e-6)

    # 额外做一个范围检查，避免出现明显异常值。
    assert np.all((result_values > 250.0) & (result_values < 320.0))


def test_official_lapse_rate_algorithm() -> None:
    """验证 LapseRate 与官方 KGO、原算法结果一致。"""
    files = {
        "temperature": LAPSE_CLI_INPUT_DIR / "temperature_at_screen_level.nc",
        "orography": LAPSE_CLI_INPUT_DIR / "ukvx_orography.nc",
        "landmask": LAPSE_CLI_INPUT_DIR / "ukvx_landmask.nc",
        "kgo": LAPSE_DATA_DIR / "kgo.nc",
        "original": LAPSE_DATA_DIR / "original_lapse_rate_result.nc",
    }
    _assert_files_exist(list(files.values()))

    temperature = xr.open_dataset(files["temperature"], decode_timedelta=False)["air_temperature"]
    orography = xr.open_dataset(files["orography"], decode_timedelta=False)["surface_altitude"]
    landmask = xr.open_dataset(files["landmask"], decode_timedelta=False)["land_binary_mask"]
    expected = xr.open_dataset(files["kgo"], decode_timedelta=False)["air_temperature_lapse_rate"].values
    original = xr.open_dataset(files["original"], decode_timedelta=False)["air_temperature_lapse_rate"].values

    result = LapseRate()(temperature, orography, landmask)
    result_values = _as_spatial(
        result.values if isinstance(result, xr.DataArray) else np.asarray(result)
    )
    expected_values = _as_spatial(expected)
    original_values = _as_spatial(original)

    assert result_values.shape == expected_values.shape
    np.testing.assert_allclose(result_values, expected_values, atol=1e-6, rtol=1e-6)
    np.testing.assert_allclose(result_values, original_values, atol=1e-6, rtol=1e-6)

    assert np.all((result_values >= -0.01) & (result_values <= 0.03))

