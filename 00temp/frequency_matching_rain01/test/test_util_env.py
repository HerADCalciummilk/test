# -*- coding: utf-8 -*-
"""util_env 与 qpf_fm.ini 路径解析测试。"""
from utils.util_env import get_resolved_paths
from utils.util_paths import repo_root


def test_call_override_replaces_path_then_clears(tmp_path):
    from utils.util_env import clear_call_overrides, get_resolved_paths, set_call_overrides

    target = tmp_path / "custom_sta.info"
    before = get_resolved_paths()["station_info"]
    set_call_overrides({"log_file": str(tmp_path / "YYYYMMDD.txt"), "station_info": str(target)})
    try:
        paths = get_resolved_paths()
        assert paths["station_info"] == target.resolve()
        assert paths["log_file_template"] == (tmp_path / "YYYYMMDD.txt").resolve()
        assert paths["config_json"].name == "config.json"
        assert paths["mask_file"].name == "mask010.dat"
    finally:
        clear_call_overrides()
    assert get_resolved_paths()["station_info"] == before


def test_util_env_default_paths_under_repo():
    paths = get_resolved_paths()
    root = repo_root()
    assert paths["config_json"] == root / "resource" / "config.json"
    assert paths["path_json"] == root / "resource" / "path.json"
    assert paths["station_info"] == root / "resource" / "sta.info"
    assert paths["mask_file"] == root / "resource" / "mask010.dat"
