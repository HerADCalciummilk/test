#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""QPE CLI 统一入口 process 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from radar_qpe_retrieval.cli.qpe import process
from radar_qpe_retrieval.src.qpe import QPEPlugin

INPUT_DIR = Path(__file__).resolve().parents[1] / "test_data" / "qpe" / "cli_input"
ACHN_REFL = INPUT_DIR / "ACHN_CREF000_20240612_070000.nc"
HYDRO_REFL = INPUT_DIR / "hydro_corrected_reflectivity.nc"
HYDRO_ATT = INPUT_DIR / "hydro_specific_attenuation.nc"
HYDRO_CLASS = INPUT_DIR / "hydro_radar_echo_classification.nc"
Z9010_REFL = INPUT_DIR / "Z9010_20250724192400_refl_volume.nc"
Z9010_KDP = INPUT_DIR / "Z9010_20250724192400_kdp_volume.nc"


def _require_path(path: Path) -> Path:
    if not path.is_file():
        pytest.skip(f"test input not found: {path}")
    return path


def _read_result_nc(path: Path, value_name: str | None = None) -> np.ndarray:
    data = meb.read_griddata_from_nc(str(path), value_name=value_name)
    return np.asarray(data.values, dtype=np.float32)


def _normalize_expected_after_cli_write(values: np.ndarray) -> np.ndarray:
    """按 CLI 写盘规则归一化期望值，避免缺测编码导致的 NaN 位置差异。"""
    arr = np.asarray(values, dtype=np.float32).copy()
    invalid = ~np.isfinite(arr)
    invalid |= np.abs(arr) >= np.float32(1e19)
    invalid |= arr <= np.float32(-1e6)
    invalid |= np.abs(arr + 2147483.648) < np.float32(1.0)
    arr[invalid] = np.nan
    return arr


def test_process_z_matches_plugin(tmp_path):
    """process(method='z') 输出应与 QPEPlugin(method='z') 一致。"""
    refl_path = _require_path(ACHN_REFL)
    out_path = tmp_path / "est_rain_rate_z.nc"

    process("z", refl_path=str(refl_path), output_path=str(out_path))

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = QPEPlugin(method="z").process(refl=refl)
    actual = _read_result_nc(out_path)
    expected_values = _normalize_expected_after_cli_write(expected.values)
    np.testing.assert_allclose(actual, expected_values, equal_nan=True)


def test_process_zpoly_matches_plugin(tmp_path):
    """process(method='zpoly') 输出应与 QPEPlugin(method='zpoly') 一致。"""
    refl_path = _require_path(ACHN_REFL)
    out_path = tmp_path / "est_rain_rate_zpoly.nc"

    result = process("zpoly", refl_path=str(refl_path), output_path=str(out_path))

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = QPEPlugin(method="zpoly").process(refl=refl)
    np.testing.assert_allclose(
        np.asarray(result.values, dtype=np.float32),
        np.asarray(expected.values, dtype=np.float32),
        equal_nan=True,
    )
    assert out_path.is_file()


def test_process_ztor_matches_plugin(tmp_path):
    """process(method='ztor') 输出应与 QPEPlugin(method='ztor') 一致。"""
    refl_path = _require_path(ACHN_REFL)
    out_path = tmp_path / "ztor.nc"

    result = process(
        "ztor",
        refl_path=str(refl_path),
        ztor_a=300.0,
        ztor_b=1.4,
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    expected = QPEPlugin(method="ztor", ztor_a=300.0, ztor_b=1.4).process(refl=refl)
    np.testing.assert_allclose(
        np.asarray(result.values, dtype=np.float32),
        np.asarray(expected.values, dtype=np.float32),
        equal_nan=True,
    )
    assert expected.name == "NWS_primary_prate"
    assert out_path.is_file()


def test_process_kdp_matches_plugin(tmp_path):
    """process(method='kdp') 输出应与 QPEPlugin(method='kdp') 一致。"""
    kdp_path = _require_path(Z9010_KDP)
    out_path = tmp_path / "est_rain_rate_kdp.nc"

    process("kdp", kdp_path=str(kdp_path), output_path=str(out_path))

    kdp = meb.read_griddata_from_nc(str(kdp_path))
    expected = QPEPlugin(method="kdp").process(kdp=kdp)
    actual = _read_result_nc(out_path)
    expected_values = _normalize_expected_after_cli_write(expected.values)
    np.testing.assert_allclose(actual, expected_values, equal_nan=True)


def test_process_zkdp_matches_plugin(tmp_path):
    """process(method='zkdp') 输出应与 QPEPlugin(method='zkdp') 一致。"""
    refl_path = _require_path(Z9010_REFL)
    kdp_path = _require_path(Z9010_KDP)
    out_path = tmp_path / "est_rain_rate_zkdp.nc"

    process(
        "zkdp",
        refl_path=str(refl_path),
        kdp_path=str(kdp_path),
        thresh=40.0,
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    kdp = meb.read_griddata_from_nc(str(kdp_path))
    expected = QPEPlugin(method="zkdp", thresh=40.0, thresh_max=True).process(
        refl=refl, kdp=kdp,
    )
    actual = _read_result_nc(out_path)
    expected_values = _normalize_expected_after_cli_write(expected.values)
    np.testing.assert_allclose(actual, expected_values, equal_nan=True)


def test_process_hydro_matches_plugin(tmp_path):
    """process(method='hydro') 输出应与 QPEPlugin(method='hydro') 一致。"""
    refl_path = _require_path(HYDRO_REFL)
    att_path = _require_path(HYDRO_ATT)
    hydro_path = _require_path(HYDRO_CLASS)
    out_path = tmp_path / "est_rain_rate_hydro.nc"

    process(
        "hydro",
        refl_path=str(refl_path),
        att_path=str(att_path),
        hydro_path=str(hydro_path),
        thresh=0.04,
        output_path=str(out_path),
    )

    refl = meb.read_griddata_from_nc(str(refl_path))
    att = meb.read_griddata_from_nc(str(att_path))
    hydro = meb.read_griddata_from_nc(str(hydro_path))
    expected = QPEPlugin(method="hydro", thresh=0.04, thresh_max=False).process(
        refl=refl, att=att, hydro=hydro,
    )
    actual = _read_result_nc(out_path)
    expected_values = _normalize_expected_after_cli_write(expected.values)
    np.testing.assert_allclose(actual, expected_values, equal_nan=True)
