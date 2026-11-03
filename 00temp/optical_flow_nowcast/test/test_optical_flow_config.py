# -*- coding: utf-8 -*-
"""ini 补齐与命令行入口。不导入光流插件。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from cli.extrapolation_plugin_cli import build_parser as build_extrapolation_parser
from cli.linda_plugin_cli import build_parser as build_linda_parser
from cli.lk_plugin_cli import build_parser as build_lk_parser
from cli.sprog_plugin_cli import build_parser as build_sprog_parser
from cli.steps_plugin_cli import build_parser as build_steps_parser
from utils.util_env import clear_ini_cache, resolve_args


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    for name in ("src", "cli", "resource", "test", "docs", "utils"):
        assert (_ROOT / name).is_dir(), f"missing directory: {name}"
    for name in (
        "lk_plugin.py",
        "extrapolation_plugin.py",
        "linda_plugin.py",
        "sprog_plugin.py",
        "steps_plugin.py",
    ):
        assert (_ROOT / "src" / name).is_file()
    for name in (
        "lk_plugin_cli.py",
        "extrapolation_plugin_cli.py",
        "linda_plugin_cli.py",
        "sprog_plugin_cli.py",
        "steps_plugin_cli.py",
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


def test_cli_omitted_args_are_none() -> None:
    lk_args = build_lk_parser().parse_args([])
    extrap_args = build_extrapolation_parser().parse_args([])
    sprog_args = build_sprog_parser().parse_args([])
    linda_args = build_linda_parser().parse_args([])
    steps_args = build_steps_parser().parse_args([])
    assert lk_args.precip is None
    assert lk_args.dense is None
    assert lk_args.fd_method is None
    assert extrap_args.timesteps is None
    assert extrap_args.measure_time is None
    assert sprog_args.conditional is None
    assert linda_args.add_perturbations is None
    assert steps_args.return_output is None
    assert steps_args.precip_thr is None
