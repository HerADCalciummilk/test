# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from utils.util_env import clear_ini_cache, resolve_args


def setup_module() -> None:
    clear_ini_cache()


def test_defaults_come_from_ini() -> None:
    got = resolve_args()
    assert got["mode"] == "lonlat-to-equal"
    assert got["backend"] == "cartopy"
    assert got["projection_extent"] == [83.0, 138.0, 12.0, 53.0]
    assert got["secant_latitudes"] == [25.0, 47.0]
    assert got["grid_distance"] == 1000.0
    assert got["lonlat_extent"] == [83.0, 138.0, 12.0, 53.0]
    assert got["grid_spacing"] == 0.1
    assert got["regrid_mode"] == "bilinear"


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        mode="equal-to-lonlat",
        backend="iris",
        grid_spacing=0.05,
        lonlat_extent="70,140,15,55",
        grid_distance=5000,
    )
    assert got["mode"] == "equal-to-lonlat"
    assert got["backend"] == "iris"
    assert got["grid_spacing"] == 0.05
    assert got["lonlat_extent"] == [70.0, 140.0, 15.0, 55.0]
    assert got["grid_distance"] == 5000
    assert got["regrid_mode"] == "bilinear"


def test_invalid_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        resolve_args(mode="meteva-to-cube")


def test_invalid_backend() -> None:
    with pytest.raises(ValueError, match="backend"):
        resolve_args(backend="pyproj")


def test_merge_params_entry_imports() -> None:
    from cli.coordinate_projection_transform_cli import process

    assert callable(process)


def test_cartopy_merge_params_entry_imports() -> None:
    from cli.coordinate_projection_transform_cartopy_cli import process

    assert callable(process)
