# -*- coding: utf-8 -*-
"""util_env 路径与参数解析。"""
from pathlib import Path

from utils.util_env import get_repo_root, get_resolved_paths, get_run_params


def test_repo_root_is_package_root():
    root = Path(get_repo_root())
    assert (root / "resource" / "gust_factor.ini").is_file()
    assert (root / "src" / "gust_factor.py").is_file()


def test_resolved_paths_defaults():
    paths = get_resolved_paths()
    root = Path(get_repo_root())
    assert paths["station_csv_dir"].startswith(str(root))
    assert "gust_factor.json" in paths["factor_path"].replace("\\", "/")


def test_run_params_defaults():
    p = get_run_params()
    assert p["mode"] == "all"
    assert p["fore_hours"] == (24, 48, 72)
    assert p["fore_hour"] == 24
