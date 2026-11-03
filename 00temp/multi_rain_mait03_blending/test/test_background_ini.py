# -*- coding: utf-8 -*-
from pathlib import Path

from mait_3_plugin_util import _analysis_background_ini
from utils.util_env import get_resolved_paths, get_repo_root


def test_analysis_background_ini_reads_resource_file():
    root = Path(get_repo_root())
    bg = root / "resource" / "para_3_background.ini"
    templates = _analysis_background_ini(str(bg))
    assert "ecModel" in templates
    assert templates["ecModel"].endswith(".m4")
    assert "TTT" in templates["ecModel"]


def test_resolved_background_ini_exists():
    paths = get_resolved_paths()
    assert Path(paths["background_ini"]).is_file()


def test_missing_background_ini_returns_empty():
    assert _analysis_background_ini("") == {}
    assert _analysis_background_ini(r"D:\no_such_para_3_background.ini") == {}
