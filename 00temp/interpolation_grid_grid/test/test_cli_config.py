# -*- coding: utf-8 -*-
"""``@merge_params`` 合参、``resource/conf.ini`` 与 CLI 校验。"""
from __future__ import annotations

import configparser
import inspect
from pathlib import Path
from typing import get_type_hints

import pytest

from cli.interpolation_grid_grid_cli import (
    _as_float_list,
    _normalize_method,
    _resolve_io_type,
    process,
)
from utils.merge_params import collect_merged_params

_PKG = Path(__file__).resolve().parents[1]
_CLI_FILE = str(_PKG / "cli" / "interpolation_grid_grid_cli.py")
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
    got = _merge({"grid": r"D:\grid.nc", "domain": "20,50,70,140,0.1,0.1"})
    assert got["method"] == "linear"
    assert got["grid"] == r"D:\grid.nc"
    assert got["outer_value"] == 0.0
    assert got["mdtol"] == 1.0
    assert got["spherical"] is True
    assert got["domain"] == [20.0, 50.0, 70.0, 140.0, 0.1, 0.1]


def test_explicit_string_values_are_cast() -> None:
    got = _merge(
        {
            "method": "conservative",
            "grid": r"D:\grid.nc",
            "glon": "70,140,0.25",
            "glat": "15,55,0.25",
            "outer_value": "-999.0",
            "mdtol": "0.25",
            "spherical": "false",
        }
    )
    assert got["method"] == "conservative"
    assert got["outer_value"] == -999.0
    assert got["mdtol"] == 0.25
    assert got["spherical"] is False
    assert got["glon"] == [70.0, 140.0, 0.25]
    assert got["glat"] == [15.0, 55.0, 0.25]


def test_input_config_overrides_default_ini(tmp_path: Path) -> None:
    alt = tmp_path / "alt.ini"
    alt.write_text("[cli]\nmethod=cubic\n[params]\nouter_value=-1\n", encoding="utf-8")
    got = _merge({"config": str(alt), "grid": r"D:\grid.nc", "domain": "20,50,70,140,0.1,0.1"})
    assert got["method"] == "cubic"
    assert got["outer_value"] == -1.0
    # 显性参数压过输入 ini
    got2 = _merge({"config": str(alt), "method": "nearest", "outer_value": "5"})
    assert got2["method"] == "nearest"
    assert got2["outer_value"] == 5.0


def test_normalize_method() -> None:
    assert _normalize_method("linear") == "linear"
    assert _normalize_method("nearest") == "nearest"
    assert _normalize_method("cubic") == "cubic"
    assert _normalize_method("conservative") == "conservative"
    with pytest.raises(ValueError, match="method"):
        _normalize_method("area_weighted")
    with pytest.raises(ValueError, match="method"):
        _normalize_method("interp_gg_linear")
    with pytest.raises(ValueError, match="method"):
        _normalize_method("unknown")


def test_required_grid_raises_when_empty() -> None:
    with pytest.raises(ValueError, match="grid"):
        process(domain="20,50,70,140,0.1,0.1")


def test_target_grid_required() -> None:
    with pytest.raises(ValueError, match="目标网格"):
        process(grid=r"D:\grid.nc")


def test_glon_without_glat_raises() -> None:
    with pytest.raises(ValueError, match="glon 与 glat"):
        process(grid=r"D:\grid.nc", glon="70,140,0.25")


def test_resolve_io_type_by_extension_and_explicit() -> None:
    assert _resolve_io_type(r"D:\a.nc") == "nc"
    assert _resolve_io_type(r"D:\a.NC") == "nc"
    assert _resolve_io_type(r"D:\a.m4") == "m4"
    assert _resolve_io_type(r"D:\no_ext") == "m4"
    assert _resolve_io_type(r"D:\a.m4", "nc") == "nc"
    assert _resolve_io_type(r"D:\a.nc", "m4") == "m4"
    with pytest.raises(ValueError, match="nc 或 m4"):
        _resolve_io_type(r"D:\a.nc", "grib")


def test_as_float_list_length_validation() -> None:
    assert _as_float_list("20,50,70,140,0.1,0.1", "domain", 6) == [
        20.0,
        50.0,
        70.0,
        140.0,
        0.1,
        0.1,
    ]
    with pytest.raises(ValueError, match="6 个数"):
        _as_float_list("20,50,70", "domain", 6)
