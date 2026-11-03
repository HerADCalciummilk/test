# -*- coding: utf-8 -*-
"""util_env 路径与参数解析。"""
from pathlib import Path

from utils.util_env import (
    build_glon_glat,
    get_linear_params,
    get_repo_root,
    get_resolved_paths,
)


def test_repo_root_is_package_root():
    root = Path(get_repo_root())
    assert (root / "resource" / "interp_gg_linear.ini").is_file()
    assert (root / "src" / "runner.py").is_file()


def test_resolved_paths_defaults():
    paths = get_resolved_paths()
    root = Path(get_repo_root())
    assert paths["output_path"].startswith(str(root))
    assert "gg_linear.m4" in paths["output_path"].replace("\\", "/")


def test_linear_params_defaults():
    p = get_linear_params()
    assert p["used_coords"] == "xy"
    assert p["outer_value"] == 0.0
    assert p["grid_type"] == "m4"


def test_build_glon_glat_from_domain():
    glon, glat = build_glon_glat(domain=[20, 50, 70, 140, 0.1, 0.1])
    assert glon == [70.0, 140.0, 0.1]
    assert glat == [20.0, 50.0, 0.1]
