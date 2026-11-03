# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from cli.__main__ import _build_arg_parser  # noqa: E402
from utils.util_env import (  # noqa: E402
    clear_ini_cache,
    get_algo_constants,
    get_run_defaults,
    resolve_process_args,
)


def setup_module():
    clear_ini_cache()


def test_ini_defaults():
    cfg = get_run_defaults()
    assert cfg["main_uv"] == []
    assert cfg["ass_uv"] == []
    assert cfg["output_dir"].endswith("resource" + "\\output") or cfg["output_dir"].endswith(
        "resource/output"
    )
    assert cfg["output_prefix"] == ["fft_merge"]
    assert cfg["feature_border"] == 128
    assert cfg["max_iterations"] == 1024
    assert cfg["move_percent"] == 1.0
    assert cfg["write_linear_compare"] is True
    assert cfg["is_multi"] is False
    assert cfg["pro_count"] == 4
    consts = get_algo_constants()
    assert consts == {
        "weight_value": 0.1,
        "power_model": 2,
        "l_scale": 1,
        "reflect_pad": 25,
    }


def test_explicit_overrides_ini():
    got = resolve_process_args(
        main_uv_path="main.m11",
        ass_uv_path=["a.m11", "b.m11"],
        output_dir="out",
        output_prefix="case",
        feature_border=64,
        max_iterations=16,
        move_percent=0.5,
        write_linear_compare=False,
        is_multi=True,
        pro_count=2,
    )
    assert got["main_uv_path"] == "main.m11"
    assert got["ass_uv_path"] == ["a.m11", "b.m11"]
    assert got["output_dir"] == "out"
    assert got["feature_border"] == 64
    assert got["is_multi"] is True
    assert got["pro_count"] == 2
    assert got["write_linear_compare"] is False


def test_missing_paths_use_preset_output_then_raise():
    with pytest.raises(ValueError, match="main_uv"):
        resolve_process_args()
    got = resolve_process_args(main_uv_path="m.m11", ass_uv_path="a.m11")
    assert got["output_prefix"] == "fft_merge"
    assert got["feature_border"] == 128
    assert got["output_dir"]


def test_cli_omitted_args_are_none():
    args = _build_arg_parser().parse_args([])
    assert args.main_uv_path is None
    assert args.ass_uv_path is None
    assert args.weight_value is None
    assert args.power_model is None
    assert args.l_scale is None
    assert args.reflect_pad is None
    assert args.output_dir is None
    assert args.output_prefix is None
    assert args.feature_border is None
    assert args.max_iterations is None
    assert args.move_percent is None
    assert args.write_linear_compare is None
    assert args.is_multi is None
    assert args.pro_count is None


def test_cli_flags():
    args = _build_arg_parser().parse_args(["--is-multi", "--no-write-linear-compare", "--pro-count", "2"])
    assert args.is_multi is True
    assert args.write_linear_compare is False
    assert args.pro_count == 2
