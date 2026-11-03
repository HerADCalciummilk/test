# -*- coding: utf-8 -*-
"""util_env 路径与参数解析。"""
from pathlib import Path

from utils.util_env import get_merge_params, get_repo_root, get_resolved_paths


def test_repo_root_is_package_root():
    root = Path(get_repo_root())
    assert (root / "resource" / "grid_stat_merge.ini").is_file()
    assert (root / "src" / "runner.py").is_file()


def test_resolved_paths_defaults():
    paths = get_resolved_paths()
    root = Path(get_repo_root())
    assert paths["output_path"].startswith(str(root))
    assert "merge.m4" in paths["output_path"].replace("\\", "/")


def test_merge_params_defaults():
    p = get_merge_params()
    assert p["R"] == 200.0
    assert p["b_use_heatflux_equation"] is False
    assert p["hf_eq_iter_nums"] == 20
    assert p["sta_val_col"] == "data0"
