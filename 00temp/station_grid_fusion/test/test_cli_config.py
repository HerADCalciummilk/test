# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from cli.fusion_main import build_parser
from utils.util_env import clear_ini_cache, resolve_args, resolve_module


def setup_module() -> None:
    clear_ini_cache()


def test_defaults_come_from_ini() -> None:
    assert resolve_module() == "total"
    got = resolve_args(sta=r"D:\sta.csv", grid=r"D:\grid.nc")
    assert got["module"] == "total"
    assert got["sta"] == r"D:\sta.csv"
    assert got["grid"] == r"D:\grid.nc"
    assert got["background"] is None
    assert got["effect_r"] == 1000
    assert got["near_num"] == 8
    assert got["decrease"] == 2
    assert got["delta_effect_r"] == 400
    assert got["delta_near_num"] == 10
    assert got["delta_decrease"] == 2


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


def test_required_paths_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="sta"):
        resolve_args(grid=r"D:\grid.nc")
    with pytest.raises(ValueError, match="grid"):
        resolve_args(sta=r"D:\sta.csv")


def test_invalid_module() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module("unknown")


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.module is None
    assert args.sta is None
    assert args.grid is None
    assert args.effect_r is None
    assert args.half_r is None
