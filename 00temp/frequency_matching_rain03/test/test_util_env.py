# -*- coding: utf-8 -*-
from pathlib import Path

from utils.util_env import get_resolved_paths
from utils.util_paths import repo_root


def test_call_override_replaces_path_then_clears(tmp_path):
    from utils.util_env import clear_call_overrides, get_resolved_paths, set_call_overrides

    target = tmp_path / "mask_custom.dat"
    before = get_resolved_paths()["mask_file"]
    set_call_overrides({"mask_file": str(target)})
    try:
        assert get_resolved_paths()["mask_file"] == target.resolve()
        assert get_resolved_paths()["station_info"].name == "sta.info"
    finally:
        clear_call_overrides()
    assert get_resolved_paths()["mask_file"] == before


def test_util_env_defaults():
    paths = get_resolved_paths()
    root = repo_root()
    assert paths["path_json"] == root / "resource" / "path.json"
    assert paths["config_json"] == root / "resource" / "config.json"
    assert paths["station_info"] == root / "resource" / "sta.info"
    assert paths["mask_file"] == root / "resource" / "mask010.dat"
