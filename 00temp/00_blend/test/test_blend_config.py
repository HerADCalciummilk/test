# -*- coding: utf-8 -*-
"""ini 补齐与目录结构。"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

from utils.util_env import clear_ini_cache, resolve_args


def _load_process():
    path = Path(__file__).resolve().parents[1] / "cli" / "00_blend_cli.py"
    spec = importlib.util.spec_from_file_location("_blend_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process


def setup_module() -> None:
    clear_ini_cache()


def test_project_layout() -> None:
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"
    assert (root / "src" / "weight_blending.py").is_file()


def test_defaults_come_from_ini() -> None:
    got = resolve_args()
    assert got["weight_power"] == -2.0
    assert got["tolerate_period_mismatch"] is False


def test_explicit_overrides_ini() -> None:
    got = resolve_args(weight_power=-1, tolerate_period_mismatch=True)
    assert got["weight_power"] == -1.0
    assert got["tolerate_period_mismatch"] is True


def test_process_signature() -> None:
    process = _load_process()
    assert callable(process)
    names = inspect.signature(process).parameters
    assert "weight_power" in names
    assert "tolerate_period_mismatch" in names
    assert "config" in names
