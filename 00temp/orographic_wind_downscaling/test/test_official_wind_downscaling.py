#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""基于官方样例数据的风速降尺度算法对照测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from orographic_wind_downscaling.cli.dsc_wind_downscaling import process
from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection

DATA_DIR = Path(__file__).resolve().parents[1] / "test_data" / "wind_calculations_data"
CLI_INPUT_DIR = DATA_DIR / "cli_input"
MODEL_RESOLUTION = 1500.0
COMPARE_ATOL = 2.0e-5


def _assert_files_exist(paths: list[Path]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        pytest.skip(f"官方测试数据缺失: {missing}")


def _input_files() -> dict[str, Path]:
    return {
        "wind_speed": CLI_INPUT_DIR / "input.nc",
        "sigma": CLI_INPUT_DIR / "sigma.nc",
        "target_orography": CLI_INPUT_DIR / "highres_orog.nc",
        "standard_orography": CLI_INPUT_DIR / "standard_orog.nc",
        "silhouette_roughness": CLI_INPUT_DIR / "a_over_s.nc",
        "vegetative_roughness": CLI_INPUT_DIR / "veg.nc",
        "kgo": DATA_DIR / "kgo.nc",
        "original": DATA_DIR / "original_algorithm_result.nc",
    }


def _clean_values(values: np.ndarray) -> np.ndarray:
    cleaned = np.asarray(values, dtype=np.float32).copy()
    cleaned = np.nan_to_num(cleaned, nan=0.0, posinf=0.0, neginf=0.0)
    cleaned[cleaned == -32767] = 0.0
    return cleaned


def _to_spatial_values(data: xr.DataArray | np.ndarray) -> np.ndarray:
    values = data.values if isinstance(data, xr.DataArray) else data
    return _clean_values(np.squeeze(np.asarray(values)))


def _load_reference(path: Path, variable_name: str) -> xr.DataArray:
    with xr.open_dataset(path, decode_timedelta=False) as dataset:
        return dataset[variable_name].load()


def test_official_roughness_correction_matches_kgo_and_original() -> None:
    """验证 RoughnessCorrection 与官方 KGO、原算法结果一致。"""
    files = _input_files()
    _assert_files_exist(list(files.values()))

    wind_speed = xr.open_dataarray(files["wind_speed"], decode_timedelta=False)
    auxiliary = {
        key: xr.open_dataarray(files[key], decode_timedelta=False)
        for key in (
            "silhouette_roughness",
            "sigma",
            "target_orography",
            "standard_orography",
            "vegetative_roughness",
        )
    }
    kgo = _load_reference(files["kgo"], "wind_speed")
    original = _load_reference(files["original"], "wind_speed_processed")

    plugin = RoughnessCorrection(
        auxiliary["silhouette_roughness"],
        auxiliary["sigma"],
        auxiliary["target_orography"],
        auxiliary["standard_orography"],
        MODEL_RESOLUTION,
        z0=auxiliary["vegetative_roughness"],
    )
    result = plugin.process(wind_speed)
    result_values = _to_spatial_values(result)
    kgo_values = _to_spatial_values(kgo)
    original_values = _to_spatial_values(original)

    assert result_values.shape == kgo_values.shape == original_values.shape
    np.testing.assert_allclose(result_values, kgo_values, atol=COMPARE_ATOL, rtol=0.0)
    np.testing.assert_allclose(result_values, original_values, atol=COMPARE_ATOL, rtol=0.0)


def test_official_cli_matches_kgo_and_original() -> None:
    """验证 CLI process() 与官方 KGO、原算法结果一致。"""
    files = _input_files()
    _assert_files_exist(list(files.values()))

    result = process(
        str(files["wind_speed"]),
        str(files["sigma"]),
        str(files["target_orography"]),
        str(files["standard_orography"]),
        str(files["silhouette_roughness"]),
        MODEL_RESOLUTION,
        vegetative_roughness_path=str(files["vegetative_roughness"]),
    )
    kgo = _load_reference(files["kgo"], "wind_speed")
    original = _load_reference(files["original"], "wind_speed_processed")

    result_values = _to_spatial_values(result)
    kgo_values = _to_spatial_values(kgo)
    original_values = _to_spatial_values(original)

    assert result_values.shape == kgo_values.shape == original_values.shape
    np.testing.assert_allclose(result_values, kgo_values, atol=COMPARE_ATOL, rtol=0.0)
    np.testing.assert_allclose(result_values, original_values, atol=COMPARE_ATOL, rtol=0.0)
