# -*- coding: utf-8 -*-
"""``@merge_params`` 合参、``resource/conf.ini`` 与 CLI 校验。"""
from __future__ import annotations

import configparser
import inspect
from pathlib import Path
from typing import get_type_hints

import pytest

from cli.interpolation_grid_station_cli import (
    _normalize_method,
    _resolve_grid_type,
    _resolve_sta_type,
    process,
)
from utils.merge_params import collect_merged_params

_PKG = Path(__file__).resolve().parents[1]
_CLI_FILE = str(_PKG / "cli" / "interpolation_grid_station_cli.py")
_CONF_INI = _PKG / "resource" / "conf.ini"
_RAW = process.__wrapped__
_SIG = inspect.signature(_RAW)
_PRESETS = {
    name: p.default
    for name, p in _SIG.parameters.items()
    if p.default is not inspect.Parameter.empty
}
_ANNOTATIONS = get_type_hints(_RAW)
_PARAM_NAMES = list(_SIG.parameters)


def _merge(external: dict) -> dict:
    return collect_merged_params(
        external,
        anchor_file=_CLI_FILE,
        presets=_PRESETS,
        annotations=_ANNOTATIONS,
        param_names=_PARAM_NAMES,
    )


def test_ini_keys_match_process_params_and_are_unique() -> None:
    parser = configparser.ConfigParser()
    parser.read(_CONF_INI, encoding="utf-8")
    seen = set()
    for section in parser.sections():
        for key in parser.options(section):
            assert key not in seen, f"conf.ini 重复键: {key}"
            seen.add(key)
            assert key in _SIG.parameters, f"conf.ini 键不在 process 形参中: {key}"


def test_defaults_from_ini_and_signature() -> None:
    got = _merge({"grid": r"D:\grid.nc", "sta": r"D:\sta.csv"})
    assert got["method"] == "linear"
    assert got["grid"] == r"D:\grid.nc"
    assert got["sta"] == r"D:\sta.csv"
    assert got["used_coords"] == "xy"


def test_explicit_string_values_are_cast() -> None:
    got = _merge(
        {
            "method": "nearest",
            "grid": r"D:\grid.nc",
            "sta": r"D:\sta.m3",
            "used_coords": "xyz",
            "output": r"D:\out.csv",
        }
    )
    assert got["method"] == "nearest"
    assert got["used_coords"] == "xyz"
    assert got["output"] == r"D:\out.csv"


def test_input_config_overrides_default_ini(tmp_path: Path) -> None:
    alt = tmp_path / "alt.ini"
    alt.write_text(
        "[cli]\nmethod=cubic\n[params]\nused_coords=xydt\n", encoding="utf-8"
    )
    got = _merge({"config": str(alt), "grid": r"D:\grid.nc", "sta": r"D:\sta.csv"})
    assert got["method"] == "cubic"
    assert got["used_coords"] == "xydt"
    got2 = _merge(
        {
            "config": str(alt),
            "method": "nearest",
            "used_coords": "xy",
            "grid": r"D:\grid.nc",
            "sta": r"D:\sta.csv",
        }
    )
    assert got2["method"] == "nearest"
    assert got2["used_coords"] == "xy"


def test_normalize_method() -> None:
    assert _normalize_method("linear") == "linear"
    assert _normalize_method("nearest") == "nearest"
    assert _normalize_method("cubic") == "cubic"
    with pytest.raises(ValueError, match="method"):
        _normalize_method("interp_gs_linear")
    with pytest.raises(ValueError, match="method"):
        _normalize_method("unknown")


def test_required_inputs_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="grid"):
        process(sta=r"D:\sta.csv")
    with pytest.raises(ValueError, match="sta"):
        process(grid=r"D:\grid.nc")


def test_resolve_types_by_extension() -> None:
    assert _resolve_grid_type(r"D:\a.nc") == "nc"
    assert _resolve_grid_type(r"D:\a.m4") == "m4"
    assert _resolve_grid_type(r"D:\no_ext") == "m4"
    assert _resolve_sta_type(r"D:\a.csv") == "csv"
    assert _resolve_sta_type(r"D:\a.m3") == "m3"
    assert _resolve_sta_type(r"D:\no_ext") == "m3"


def test_resolve_types_explicit_override() -> None:
    assert _resolve_grid_type(r"D:\a.m4", "nc") == "nc"
    assert _resolve_sta_type(r"D:\a.m3", "csv") == "csv"
