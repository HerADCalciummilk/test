#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""echo_class CLI 示例脚本 process 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import pytest
import xarray as xr

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_echo_classification.cli.conv_strat_raut_main import process as conv_strat_raut
from radar_echo_classification.cli.feature_detection_main import process as feature_detection
from radar_echo_classification.cli.hydroclass_semisupervised_main import process as hydroclass_semisupervised
from radar_echo_classification.cli.steiner_conv_strat_main import process as steiner_conv_strat
from radar_echo_classification.src.echo_class import (
    ConvStratRautPlugin,
    FeatureDetectionPlugin,
    HydroclassSemisupervisedPlugin,
    SteinerConvStratPlugin,
)

CLI_INPUT = Path(__file__).resolve().parents[1] / "test_data" / "echo_class" / "cli_input"
ACHN_SMALL = CLI_INPUT / "ACHN_CREF000_20240612_070000_small.nc"
HYDRO_REFL = CLI_INPUT / "hydro_corrected_reflectivity.nc"
HYDRO_ZDR = CLI_INPUT / "hydro_corrected_differential_reflectivity.nc"
HYDRO_KDP = CLI_INPUT / "hydro_specific_differential_phase.nc"
HYDRO_RHV = CLI_INPUT / "hydro_uncorrected_cross_correlation_ratio.nc"
HYDRO_TEMP = CLI_INPUT / "hydro_temperature.nc"


def _require_path(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(f"test input not found: {path}")
    return path


def _collapse_to_2d(data) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32).squeeze()
    arr = arr.copy()
    arr[~np.isfinite(arr)] = np.nan
    arr[np.abs(arr) >= 1.0e20] = np.nan
    arr[arr <= -1.0e6] = np.nan
    if arr.ndim != 2:
        raise AssertionError(f"expected 2D array, got shape={arr.shape}")
    return arr


def _read_cli_result_2d(path: Path, value_name: str | None = None) -> np.ndarray:
    with xr.open_dataset(path, mask_and_scale=False) as ds:
        var_name = value_name or list(ds.data_vars)[0]
        arr = np.asarray(ds[var_name].values, dtype=np.float32)
    try:
        from xarray.backends.file_manager import FILE_CACHE

        FILE_CACHE.clear()
    except Exception:
        pass
    return _collapse_to_2d(arr)


def test_steiner_cli_matches_plugin(tmp_path):
    """steiner_conv_strat CLI 输出应与插件一致。"""
    refl_path = _require_path(ACHN_SMALL)
    out_path = tmp_path / "achn_steiner_cli.nc"

    steiner_conv_strat(
        str(refl_path),
        work_level=0.0,
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = SteinerConvStratPlugin(work_level=0.0)(refl)
    actual = _read_cli_result_2d(out_path)
    np.testing.assert_array_equal(actual, _collapse_to_2d(expected.values))


def test_feature_detection_cli_matches_plugin(tmp_path):
    """feature_detection CLI 输出应与插件一致。"""
    refl_path = _require_path(ACHN_SMALL)
    out_path = tmp_path / "achn_feature_cli.nc"

    feature_detection(
        str(refl_path),
        level_m=0.0,
        result_key="feature_detection",
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = FeatureDetectionPlugin(level_m=0.0)(refl)["feature_detection"]
    actual = _read_cli_result_2d(out_path)
    np.testing.assert_array_equal(actual, _collapse_to_2d(expected.values))


def test_conv_strat_raut_cli_matches_plugin(tmp_path):
    """conv_strat_raut CLI 输出应与插件一致。"""
    refl_path = _require_path(ACHN_SMALL)
    out_path = tmp_path / "achn_raut_cli.nc"

    conv_strat_raut(
        str(refl_path),
        cappi_level=0,
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = ConvStratRautPlugin(cappi_level=0)(refl)
    actual = _read_cli_result_2d(out_path)
    np.testing.assert_array_equal(actual, _collapse_to_2d(expected.values))


def test_hydroclass_cli_matches_plugin(tmp_path):
    """hydroclass_semisupervised CLI 输出应与插件一致。"""
    refl_path = _require_path(HYDRO_REFL)
    zdr_path = _require_path(HYDRO_ZDR)
    kdp_path = _require_path(HYDRO_KDP)
    rhv_path = _require_path(HYDRO_RHV)
    temp_path = _require_path(HYDRO_TEMP)
    out_path = tmp_path / "hydroclass_cli.nc"

    hydroclass_semisupervised(
        refl_path=str(refl_path),
        zdr_path=str(zdr_path),
        kdp_path=str(kdp_path),
        rhv_path=str(rhv_path),
        temp_path=str(temp_path),
        result_key="hydro",
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    zdr = meb.read_griddata_from_nc(str(zdr_path))
    kdp = meb.read_griddata_from_nc(str(kdp_path))
    rhv = meb.read_griddata_from_nc(str(rhv_path))
    temp = meb.read_griddata_from_nc(str(temp_path))
    expected = HydroclassSemisupervisedPlugin()(
        refl=refl, zdr=zdr, kdp=kdp, rhv=rhv, temp=temp
    )["hydro"]
    actual = _read_cli_result_2d(out_path, value_name="radar_echo_classification")
    np.testing.assert_array_equal(actual, _collapse_to_2d(expected.values))
