# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from cli.interpolation_grid_grid_cli import build_parser
from utils.util_env import clear_ini_cache, resolve_args, resolve_io_type, resolve_module


def setup_module() -> None:
    clear_ini_cache()


def test_defaults_come_from_ini() -> None:
    assert resolve_module() == "linear"
    got = resolve_args(grid=r"D:\grid.nc", domain="20,50,70,140,0.1,0.1")
    assert got["module"] == "linear"
    assert got["grid"] == r"D:\grid.nc"
    assert got["used_coords"] == "xy"
    assert got["outer_value"] == 0.0
    assert got["domain"] == [20.0, 50.0, 70.0, 140.0, 0.1, 0.1]
    assert got["grid_type"] == "nc"
    assert got["grid_template_type"] is None


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        module="linear",
        grid=r"D:\grid.nc",
        glon="70,140,0.25",
        glat="15,55,0.25",
        outer_value=-999.0,
    )
    assert got["outer_value"] == -999.0
    assert got["glon"] == [70.0, 140.0, 0.25]
    assert got["glat"] == [15.0, 55.0, 0.25]


def test_nearest_and_cubic_modules() -> None:
    assert resolve_module("nearest") == "nearest"
    assert resolve_module("cubic") == "cubic"
    nearest = resolve_args(module="nearest", grid=r"D:\grid.nc", domain="20,50,70,140,0.1,0.1")
    cubic = resolve_args(module="cubic", grid=r"D:\grid.nc", domain="20,50,70,140,0.1,0.1")
    assert nearest["module"] == "nearest"
    assert cubic["module"] == "cubic"
    assert nearest["outer_value"] == 0.0
    assert cubic["used_coords"] == "xy"


def test_required_grid_raises_when_empty() -> None:
    with pytest.raises(ValueError, match="grid"):
        resolve_args(domain="20,50,70,140,0.1,0.1")


def test_target_grid_required() -> None:
    with pytest.raises(ValueError, match="目标网格"):
        resolve_args(grid=r"D:\grid.nc")


def test_invalid_module() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module("unknown")


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.module is None
    assert args.grid is None
    assert args.outer_value is None
    assert args.grid_type is None
    assert args.grid_template_type is None


def test_resolve_io_type_by_extension() -> None:
    assert resolve_io_type(r"D:\a.nc") == "nc"
    assert resolve_io_type(r"D:\a.NC") == "nc"
    assert resolve_io_type(r"D:\a.m4") == "m4"
    assert resolve_io_type(r"D:\no_ext") == "m4"


def test_resolve_io_type_explicit_overrides_extension() -> None:
    assert resolve_io_type(r"D:\a.m4", "nc") == "nc"
    assert resolve_io_type(r"D:\a.nc", "m4") == "m4"
    assert resolve_io_type(r"D:\no_ext", "nc") == "nc"


def test_resolve_io_type_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="nc 或 m4"):
        resolve_io_type(r"D:\a.nc", "grib")


def test_resolve_args_grid_type_explicit() -> None:
    got = resolve_args(
        grid=r"D:\no_ext",
        grid_type="nc",
        domain="20,50,70,140,0.1,0.1",
    )
    assert got["grid_type"] == "nc"


def test_resolve_args_template_type_by_extension() -> None:
    got = resolve_args(
        grid=r"D:\src.m4",
        grid_template=r"D:\tmpl.nc",
    )
    assert got["grid_type"] == "m4"
    assert got["grid_template_type"] == "nc"
