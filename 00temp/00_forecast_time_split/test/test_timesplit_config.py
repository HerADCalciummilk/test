# -*- coding: utf-8 -*-
"""ini 补齐与目录结构。"""
from __future__ import annotations

from pathlib import Path

import pytest

from cli.cal_griddata_TimeSplit_plugin_cli import build_parser as build_timesplit_parser
from cli.readdata_fromtime_plugin_cli import build_parser as build_read_parser
from cli.timesplit_hourtomin_plugin_cli import build_parser as build_hourtomin_parser
from utils.util_env import clear_ini_cache, resolve_args, resolve_module


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    for name in (
        "cal_griddata_TimeSplit_plugin.py",
        "timesplit_hourtomin_plugin.py",
        "readdata_fromtime_plugin.py",
    ):
        assert (root / "src" / name).is_file()
    for name in (
        "cal_griddata_TimeSplit_plugin_cli.py",
        "timesplit_hourtomin_plugin_cli.py",
        "readdata_fromtime_plugin_cli.py",
    ):
        assert (root / "cli" / name).is_file()


def test_hourtomin_defaults() -> None:
    assert resolve_module("hourtomin") == "hourtomin"
    got = resolve_args(module="hourtomin")
    assert got["ntime"] == 10
    assert got["is_min"] is True
    assert got["index"] == "dtime"


def test_timesplit_requires_paths() -> None:
    with pytest.raises(ValueError, match="input_fh"):
        resolve_args(module="timesplit", output_fh="0,72,1", input_fmt="a.nc", time="2023070100")


def test_explicit_overrides_ini() -> None:
    got = resolve_args(
        module="timesplit",
        input_fh="0,72,3",
        output_fh="0,72,1",
        input_fmt="fcst.nc",
        time="2023070100",
        interp_method="linear",
        is_fill0=True,
    )
    assert got["input_fh"] == "0,72,3"
    assert got["interp_method"] == "linear"
    assert got["is_fill0"] is True
    assert got["output_fmt"] is None


def test_cli_omitted_args_are_none() -> None:
    timesplit_args = build_timesplit_parser().parse_args([])
    hour_args = build_hourtomin_parser().parse_args([])
    read_args = build_read_parser().parse_args([])
    assert timesplit_args.input_fh is None
    assert timesplit_args.is_fill0 is None
    assert hour_args.ntime is None
    assert hour_args.is_min is None
    assert read_args.file_path is None
