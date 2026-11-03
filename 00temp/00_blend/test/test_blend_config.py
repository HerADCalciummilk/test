# -*- coding: utf-8 -*-
"""ini 补齐与目录结构。"""
from __future__ import annotations

from pathlib import Path

from cli.weight_blending_cli import build_parser
from utils.util_env import clear_ini_cache, resolve_args


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


def test_cli_omitted_args_are_none() -> None:
    args = build_parser().parse_args([])
    assert args.weight_power is None
    assert args.tolerate_period_mismatch is None
