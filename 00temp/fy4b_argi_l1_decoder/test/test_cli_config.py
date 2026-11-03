# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from cli.fy4_main import build_parser
from utils.util_env import clear_ini_cache, resolve_batch, resolve_module, resolve_single


def setup_module() -> None:
    clear_ini_cache()


def test_module_and_grid_come_from_ini() -> None:
    assert resolve_module() == "batch"
    got = resolve_batch(
        input_root=r"D:\in",
        output_root=r"D:\out",
        start_time="2023010406",
        end_time="2023010423",
    )
    assert got["resolution"] == 0.04
    assert got["lat_min"] == -60.0
    assert got["lat_max"] == 60.0
    assert got["lon_half_width"] == 75.0
    assert got["channels"] == "1-15"
    assert got["resampling"] == "bilinear"
    assert got["centers"] == "1050E,1330E"
    assert got["overwrite"] is False
    assert got["recursive"] is False
    assert got["input_root"] == r"D:\in"
    assert got["start_time"] == "2023010406"


def test_explicit_overrides_ini() -> None:
    got = resolve_single(
        input_hdf=r"D:\a.HDF",
        output_dir=r"D:\case",
        resolution=0.1,
        channels="1,3",
        resampling="nearest",
    )
    assert got["input_hdf"] == r"D:\a.HDF"
    assert got["output_dir"] == r"D:\case"
    assert got["resolution"] == 0.1
    assert got["channels"] == "1,3"
    assert got["resampling"] == "nearest"
    assert got["lat_max"] == 60.0


def test_required_paths_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="input_root"):
        resolve_batch(output_root=r"D:\out", start_time="2023010406", end_time="2023010423")
    with pytest.raises(ValueError, match="input_hdf"):
        resolve_single(output_dir=r"D:\case")


def test_invalid_module() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module("unknown")


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.module is None
    assert args.input_root is None
    assert args.resolution is None
    assert args.overwrite is None
    assert args.recursive is None
