# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import inspect

import pytest

from cli.fusion_main import process
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
    assert resolve_module() == "idw"
    got = resolve_args(sta=r"D:\sta.csv", grid=r"D:\grid.nc")
    assert got["module"] == "idw"
    assert got["sta"] == r"D:\sta.csv"
    assert got["grid"] == r"D:\grid.nc"
    assert got["background"] is None
    assert got["reprocess"] is False
    assert got["effect_r"] == 1000
    assert got["near_num"] == 8
    assert got["decrease"] == 2
    assert got["sta_type"] == "csv"
    assert got["grid_type"] == "nc"
    assert got["output"] is None
    assert got["output_type"] is None


def test_background_only_ok_and_reprocess() -> None:
    got = resolve_args(sta=r"D:\sta.csv", background=r"D:\bg.nc")
    assert got["grid"] is None
    assert got["grid_type"] is None
    assert got["background"] == r"D:\bg.nc"
    assert got["background_type"] == "nc"
    assert got["reprocess"] is False
    true_got = resolve_args(
        sta=r"D:\sta.csv", background=r"D:\bg.nc", reprocess=True
    )
    assert true_got["reprocess"] is True


def test_total_alias_maps_to_idw() -> None:
    assert resolve_module("total") == "idw"


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        module="idw",
        sta=r"D:\sta.csv",
        grid=r"D:\grid.nc",
        effect_r=500,
        near_num=4,
    )
    assert got["effect_r"] == 500
    assert got["near_num"] == 4
    assert got["decrease"] == 2
    gaussian = resolve_args(module="gaussian", sta=r"D:\sta.csv", grid=r"D:\grid.nc", half_r=30)
    assert gaussian["half_r"] == 30


def test_cressman_defaults_and_override() -> None:
    got = resolve_args(module="cressman", sta=r"D:\sta.csv", grid=r"D:\grid.nc")
    assert got["module"] == "cressman"
    assert got["r_list"] == [60000.0, 40000.0, 20000.0]
    assert got["near_num"] == 100
    overridden = resolve_args(
        module="cressman",
        sta=r"D:\sta.csv",
        grid=r"D:\grid.nc",
        r_list="50000,25000",
        near_num=50,
    )
    assert overridden["r_list"] == [50000.0, 25000.0]
    assert overridden["near_num"] == 50


def test_required_paths_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="sta"):
        resolve_args(grid=r"D:\grid.nc")
    with pytest.raises(ValueError, match="grid 或 background"):
        resolve_args(sta=r"D:\sta.csv")
    with pytest.raises(ValueError, match="background"):
        resolve_args(sta=r"D:\sta.csv", grid=r"D:\grid.nc", reprocess=True)


def test_idw_reprocess_defaults_gaussian() -> None:
    got = resolve_args(
        module="idw",
        sta=r"D:\sta.csv",
        background=r"D:\bg.nc",
        reprocess=True,
    )
    assert got["module"] == "idw"
    assert got["reprocess"] is True
    assert got["gaussian"] is True
    off = resolve_args(
        module="idw",
        sta=r"D:\sta.csv",
        background=r"D:\bg.nc",
        reprocess=True,
        gaussian=False,
    )
    assert off["gaussian"] is False


def test_idw_delta_requires_background() -> None:
    with pytest.raises(ValueError, match="grid 或 background"):
        resolve_args(module="idw_delta", sta=r"D:\sta.csv")
    with pytest.raises(ValueError, match="background"):
        resolve_args(module="idw_delta", sta=r"D:\sta.csv", grid=r"D:\grid.nc")
    only_bg = resolve_args(
        module="idw_delta", sta=r"D:\sta.csv", background=r"D:\bg.nc"
    )
    assert only_bg["reprocess"] is True
    assert only_bg["gaussian"] is True
    assert only_bg["grid"] is None
    assert only_bg["background"] == r"D:\bg.nc"
    both = resolve_args(
        module="idw_delta",
        sta=r"D:\sta.csv",
        grid=r"D:\grid.nc",
        background=r"D:\bg.nc",
    )
    assert both["reprocess"] is True
    assert both["grid"] == r"D:\grid.nc"
    assert both["background"] == r"D:\bg.nc"


def test_invalid_module() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module("unknown")


def test_cli_omitted_args_are_none() -> None:
    params = inspect.signature(process).parameters
    assert params["module"].default is None
    assert params["sta"].default is None
    assert params["grid"].default is None
    assert params["background"].default is None
    assert params["reprocess"].default is None
    assert params["gaussian"].default is None
    assert params["effect_r"].default is None
    assert params["half_r"].default is None
    assert params["sta_type"].default is None
    assert params["grid_type"].default is None
    assert params["output"].default is None


def test_resolve_io_and_sta_type() -> None:
    assert resolve_io_type(r"D:\a.nc") == "nc"
    assert resolve_io_type(r"D:\a.m4") == "m4"
    assert resolve_io_type(r"D:\no_ext", "nc") == "nc"
    assert resolve_sta_type(r"D:\a.csv") == "csv"
    assert resolve_sta_type(r"D:\a.m3") == "m3"
    assert resolve_sta_type(r"D:\no_ext", "csv") == "csv"


def test_resolve_args_io_types() -> None:
    got = resolve_args(
        sta=r"D:\sta.m3",
        grid=r"D:\grid.m4",
        background=r"D:\bg.nc",
        output=r"D:\out.nc",
    )
    assert got["sta_type"] == "m3"
    assert got["grid_type"] == "m4"
    assert got["background_type"] == "nc"
    assert got["output_type"] == "nc"
    forced = resolve_args(
        sta=r"D:\no_ext",
        grid=r"D:\no_ext",
        sta_type="csv",
        grid_type="nc",
        output=r"D:\out.m4",
        output_type="m4",
    )
    assert forced["sta_type"] == "csv"
    assert forced["grid_type"] == "nc"
    assert forced["output_type"] == "m4"
