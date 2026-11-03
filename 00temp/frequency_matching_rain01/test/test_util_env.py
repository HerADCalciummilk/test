# -*- coding: utf-8 -*-
"""util_env 与 qpf_fm.ini 路径解析测试。"""
from utils.util_env import get_resolved_paths
from utils.util_paths import repo_root


def test_util_env_default_paths_under_repo():
    paths = get_resolved_paths()
    root = repo_root()
    assert paths["config_json"] == root / "resource" / "config.json"
    assert paths["path_json"] == root / "resource" / "path.json"
    assert paths["station_info"] == root / "resource" / "sta.info"
    assert paths["mask_file"] == root / "resource" / "mask010.dat"
