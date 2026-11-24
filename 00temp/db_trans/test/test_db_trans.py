# -*- coding: utf-8 -*-
"""降水强度变换数值与配置。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db_trans_plugin import DbTransPlugin
from utils.util_env import clear_ini_cache, resolve_args


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    assert (root / "src" / "db_trans_plugin.py").is_file()
    assert not (root / "src" / "dB_trans.py").is_file()


def test_db_example_values() -> None:
    result, metadata = DbTransPlugin().dB_transform(
        np.array([0.0, 0.05, 0.1, 1.0, 10.0, 100.0])
    )
    assert metadata["transform"] == "dB"
    assert result == pytest.approx([-15.0, -15.0, -10.0, 0.0, 10.0, 20.0])


def test_defaults_come_from_ini() -> None:
    got = resolve_args()
    assert got["method"] == "summary"
    assert got["values"] is None
    assert got["threshold"] == 0.1
    assert got["zerovalue"] is None
    assert got["lambda"] == 0.0
    assert got["a"] == 0.0
    assert got["inverse"] is False


def test_explicit_overrides_ini() -> None:
    got = resolve_args(method="box", values="0.1,1,10", lam=0.5, inverse=True)
    assert got["method"] == "box"
    assert got["values"] == "0.1,1,10"
    assert got["lambda"] == 0.5
    assert got["inverse"] is True
    assert got["threshold"] == 0.1


def test_required_values_raise_when_empty() -> None:
    with pytest.raises(ValueError, match="values"):
        resolve_args(method="db")


def test_plugin_db_matches_example() -> None:
    result, metadata = DbTransPlugin().process(
        [0.0, 0.05, 0.1, 1.0, 10.0, 100.0],
        method="db",
    )
    assert metadata["transform"] == "dB"
    assert np.asarray(result) == pytest.approx([-15.0, -15.0, -10.0, 0.0, 10.0, 20.0])
