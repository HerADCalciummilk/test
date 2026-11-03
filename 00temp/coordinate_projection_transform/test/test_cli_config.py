# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from cli.coordinate_projection_transform_main import build_parser
from utils.util_env import clear_ini_cache, resolve_args


def setup_module() -> None:
    clear_ini_cache()


def test_defaults_come_from_ini() -> None:
    got = resolve_args()
    assert got["mode"] == "summary"
    assert got["projection_extent"] == [83.0, 138.0, 12.0, 53.0]
    assert got["secant_latitudes"] == [25.0, 47.0]
    assert got["grid_distance"] == 1000.0
    assert got["regrid_mode"] == "bilinear"
    assert got["spatial_grid"] == "latlon"
    assert got["bounds"] == []
    assert got["near_num"] == 3
    assert got["near_distance"] == 20000.0


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        mode="lonlat-to-equal",
        grid_distance=5000,
        projection_extent="70,140,15,55",
        spatial_grid="equalarea",
    )
    assert got["mode"] == "lonlat-to-equal"
    assert got["grid_distance"] == 5000
    assert got["projection_extent"] == [70.0, 140.0, 15.0, 55.0]
    assert got["spatial_grid"] == "equalarea"
    assert got["regrid_mode"] == "bilinear"


def test_invalid_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        resolve_args(mode="unknown")


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.mode is None
    assert args.grid_distance is None
    assert args.spatial_grid is None
