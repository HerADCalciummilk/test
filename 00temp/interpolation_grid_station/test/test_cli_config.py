# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from cli.interpolation_grid_station_cli import build_parser
from utils.util_env import (
    clear_ini_cache,
    resolve_args,
    resolve_io_type,
    resolve_module,
    resolve_sta_type,
)


def setup_module() -> None:
    clear_ini_cache()


def test_defaults_come_from_ini() -> None:
    assert resolve_module() == "linear"
    got = resolve_args(grid=r"D:\grid.nc", sta=r"D:\sta.csv")
    assert got["module"] == "linear"
    assert got["grid"] == r"D:\grid.nc"
    assert got["sta"] == r"D:\sta.csv"
    assert got["used_coords"] == "xy"
    assert got["grid_type"] == "nc"
    assert got["sta_type"] == "csv"
    assert got["output"] is None
    assert got["output_type"] is None


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        module="linear",
        grid=r"D:\grid.nc",
        sta=r"D:\sta.m3",
        used_coords="xyz",
        output=r"D:\out.csv",
    )
    assert got["used_coords"] == "xyz"
    assert got["sta_type"] == "m3"
    assert got["output_type"] == "csv"


def test_nearest_and_cubic_modules() -> None:
    assert resolve_module("nearest") == "nearest"
    assert resolve_module("cubic") == "cubic"
    nearest = resolve_args(module="nearest", grid=r"D:\grid.nc", sta=r"D:\sta.csv")
    cubic = resolve_args(module="cubic", grid=r"D:\grid.nc", sta=r"D:\sta.csv")
    assert nearest["module"] == "nearest"
    assert cubic["module"] == "cubic"
    assert nearest["used_coords"] is None
    assert cubic["used_coords"] is None


def test_linear_allows_xydt() -> None:
    got = resolve_args(
        module="linear",
        grid=r"D:\grid.nc",
        sta=r"D:\sta.csv",
        used_coords="xydt",
    )
    assert got["used_coords"] == "xydt"


def test_nearest_rejects_used_coords() -> None:
    with pytest.raises(ValueError, match="used_coords"):
        resolve_args(
            module="nearest",
            grid=r"D:\grid.nc",
            sta=r"D:\sta.csv",
            used_coords="xy",
        )


def test_required_inputs_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="grid"):
        resolve_args(sta=r"D:\sta.csv")
    with pytest.raises(ValueError, match="sta"):
        resolve_args(grid=r"D:\grid.nc")


def test_invalid_module() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module("unknown")


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.module is None
    assert args.grid is None
    assert args.sta is None
    assert args.used_coords is None
    assert args.grid_type is None
    assert args.sta_type is None


def test_resolve_io_type_by_extension() -> None:
    assert resolve_io_type(r"D:\a.nc") == "nc"
    assert resolve_io_type(r"D:\a.m4") == "m4"
    assert resolve_io_type(r"D:\no_ext") == "m4"


def test_resolve_sta_type_by_extension() -> None:
    assert resolve_sta_type(r"D:\a.csv") == "csv"
    assert resolve_sta_type(r"D:\a.m3") == "m3"
    assert resolve_sta_type(r"D:\no_ext") == "m3"


def test_resolve_types_explicit_override() -> None:
    assert resolve_io_type(r"D:\a.m4", "nc") == "nc"
    assert resolve_sta_type(r"D:\a.m3", "csv") == "csv"
