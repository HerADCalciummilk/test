# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import inspect

import pytest

from cli.fy4b_argi_l1_decoder_cli import process
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
    params = inspect.signature(process).parameters
    assert params["module"].default is None
    assert params["input_root"].default is None
    assert params["resolution"].default is None
    assert params["overwrite"].default is None
    assert params["recursive"].default is None
