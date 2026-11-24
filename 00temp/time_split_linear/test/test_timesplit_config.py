# -*- coding: utf-8 -*-
"""ini 补齐与目录结构。"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from cli.time_split_linear_cli import process
from utils.util_env import clear_ini_cache, resolve_args, resolve_module


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    assert (root / "src" / "cal_griddata_TimeSplit_plugin.py").is_file()
    assert (root / "src" / "time_split_linear_plugin.py").is_file()
    assert not (root / "src" / "timesplit_hourtomin_plugin.py").is_file()
    assert not (root / "src" / "readdata_fromtime_plugin.py").is_file()
    assert (root / "cli" / "time_split_linear_cli.py").is_file()
    assert not (root / "cli" / "cal_griddata_TimeSplit_plugin_cli.py").is_file()
    assert not (root / "cli" / "timesplit_hourtomin_plugin_cli.py").is_file()
    assert not (root / "cli" / "readdata_fromtime_plugin_cli.py").is_file()


def test_timesplit_requires_paths() -> None:
    assert resolve_module("timesplit") == "timesplit"
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
    assert got["is_min"] is False
    assert got["index"] == "dtime"
    assert got["output_fmt"] is None
    minute = resolve_args(
        module="timesplit",
        input_fh="0,6,1",
        output_fh="0,360,10",
        input_fmt="fcst.nc",
        time="2023070100",
        is_min=True,
    )
    assert minute["is_min"] is True
    along_time = resolve_args(
        module="timesplit",
        input_fh="0,0,1",
        output_fh="0,120,30",
        input_fmt="fcst.nc",
        time="2023070100,2023070101,2023070102",
        index="time",
        is_min=True,
    )
    assert along_time["index"] == "time"


def test_process_omitted_args_are_none() -> None:
    params = inspect.signature(process).parameters
    assert params["input_fh"].default is None
    assert params["delta_hour"].default is None
    assert params["is_fill0"].default is None
    assert params["is_min"].default is None
    assert params["index"].default is None


def test_delta_hour_is_named() -> None:
    got = resolve_args(
        module="timesplit",
        input_fh="0,72,3",
        output_fh="0,72,1",
        input_fmt="fcst.nc",
        time="2023070100",
        delta_hour="3",
    )
    assert got["delta"] == "3"
