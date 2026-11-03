# -*- coding: utf-8 -*-
"""ini 补齐与统一 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from kalman_element_forecast_correction.cli import parse_args
from kalman_element_forecast_correction.utils.util_env import (
    clear_ini_cache,
    resolve_kalman,
    resolve_module,
    resolve_trans,
)


def setup_module() -> None:
    clear_ini_cache()


def test_module_required() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module()
    assert resolve_module("kalman_data") == "kalman"
    assert resolve_module("trans") == "trans"


def test_kalman_falls_back_to_preset() -> None:
    got = resolve_kalman(alpha=0.2)
    assert got["start_date"] == ""
    assert got["end_date"] == ""
    assert got["alpha"] == 0.2
    assert got["back_days"] == 5
    assert got["variables"] == "SWVL,STL"
    assert got["obs_end_time"] == ""
    assert got["base_dir"].endswith("Kalman_data")


def test_trans_explicit_overrides_ini() -> None:
    got = resolve_trans(date="20260401", target_base="out")
    assert got["date"] == "20260401"
    assert got["target_base"] == "out"
    assert "SWVL" in got["swvl_source"]


def test_cli_omitted_args_are_none() -> None:
    args = parse_args([])
    assert args.module is None
    assert args.start_date is None
    assert args.alpha is None
    chosen = parse_args(["--module", "kalman", "--start-date", "20260401", "--variables", "SWVL"])
    assert chosen.module == "kalman"
    assert chosen.start_date == "20260401"
    assert chosen.variables == "SWVL"
    assert chosen.back_days is None
