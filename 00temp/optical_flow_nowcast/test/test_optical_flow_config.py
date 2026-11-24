# -*- coding: utf-8 -*-
"""ini 补齐与命令行入口。不导入光流插件。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from utils.util_env import clear_ini_cache, resolve_args


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    for name in ("src", "cli", "resource", "test", "docs", "utils"):
        assert (_ROOT / name).is_dir(), f"missing directory: {name}"
    for name in (
        "lk_plugin.py",
        "lsqr_optical_flow_plugin.py",
        "lagrangian_plugin.py",
        "extrapolation_plugin.py",
        "linda_plugin.py",
        "sprog_plugin.py",
        "steps_plugin.py",
    ):
        assert (_ROOT / "src" / name).is_file()
    for name in (
        "lk_cli.py",
        "lsqr_optical_flow_cli.py",
        "extrapolation_cli.py",
        "linda_cli.py",
        "sprog_cli.py",
        "steps_cli.py",
    ):
        assert (_ROOT / "cli" / name).is_file()


def test_lk_defaults_and_keeps_typed_path() -> None:
    got = resolve_args("lk", precip="obs1.nc,obs2.nc")
    assert got["precip"] == "obs1.nc,obs2.nc"
    assert got["fd_method"] == "shitomasi"
    assert got["interp_method"] == "idwinterp2d"
    assert got["dense"] is True
    assert got["transform_method"] is None


def test_lk_requires_precip() -> None:
    with pytest.raises(ValueError, match="precip"):
        resolve_args("lk")


def test_lsqr_optical_flow_defaults() -> None:
    got = resolve_args(
        "lsqr_optical_flow",
        precip_before="model.nc",
        precip_next="obs.nc",
    )
    assert got["precip_before"] == "model.nc"
    assert got["precip_next"] == "obs.nc"
    assert got["min_window"] == "5.0,5.0"
    assert got["rain_limit"] == 0.1
    assert got["num_limit"] == 100
    assert got["verbose"] is False


def test_lsqr_optical_flow_requires_paths() -> None:
    with pytest.raises(ValueError, match="precip_before"):
        resolve_args("lsqr_optical_flow")


def test_window_lsqr_alias() -> None:
    got = resolve_args("window_lsqr", precip_before="a.nc", precip_next="b.nc")
    assert got["precip_before"] == "a.nc"


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        "extrapolation",
        precip="obs.nc",
        velocity="uv.nc",
        timesteps=6,
        extrap_method="eulerian",
        measure_time=True,
    )
    assert got["extrap_method"] == "eulerian"
    assert got["measure_time"] is True
    assert got["delta_min"] == 10
    assert got["velocity"] == "uv.nc"


def test_steps_optional_thresholds_stay_empty() -> None:
    got = resolve_args("steps", precip="a.nc", velocity="uv.nc", timesteps=3)
    assert got["n_ens_members"] == 4
    assert got["precip_thr"] is None
    assert got["vel_pert_method"] is None
    assert got["return_output"] is True

