# -*- coding: utf-8 -*-
"""util_env 路径与参数解析。"""
from pathlib import Path

from utils.util_env import (
    build_glon_glat,
    get_cressman_params,
    get_repo_root,
    get_resolved_paths,
)


def test_repo_root_is_package_root():
    root = Path(get_repo_root())
    assert (root / "resource" / "interp_sg_cressman.ini").is_file()
    assert (root / "src" / "runner.py").is_file()


def test_resolved_paths_defaults():
    paths = get_resolved_paths()
    root = Path(get_repo_root())
    assert paths["output_path"].startswith(str(root))
    assert "cressman.m4" in paths["output_path"].replace("\\", "/")


def test_cressman_params_defaults():
    p = get_cressman_params()
    assert p["r_list"] == [60000.0, 40000.0, 20000.0]
    assert p["nearNum"] == 100
    assert p["outer_value"] == 0.0


def test_build_glon_glat_from_domain():
    glon, glat = build_glon_glat(domain=[20, 50, 70, 140, 0.1, 0.1])
    assert glon == [70.0, 140.0, 0.1]
    assert glat == [20.0, 50.0, 0.1]
