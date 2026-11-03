# -*- coding: utf-8 -*-
"""配置加载与 CLI 参数解析测试。"""
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import runner
from utils.util_paths import repo_root


def test_load_path_configs_from_resource():
    base = repo_root()
    log = MagicMock()
    configs, default_key = runner._load_path_configs(base, log)
    assert default_key == "ecmwf"
    assert "ecmwf" in configs
    assert configs["ecmwf"].model_template


def test_parse_runtime_single():
    log = MagicMock()
    dts = runner._parse_runtime(["202604081130"], log)
    assert dts == [datetime(2026, 4, 8, 11, 30)]


def test_load_grid_config():
    base = repo_root()
    log = MagicMock()
    cfg = runner._load_grid_config(base, log)
    assert cfg.lon_start == 70.0
    assert cfg.dlon == 0.1


def test_resource_files_exist():
    root = repo_root()
    assert (root / "resource" / "path.json").exists()
    assert (root / "resource" / "config.json").exists()
    assert (root / "resource" / "sta.info").exists()
    payload = json.loads((root / "resource" / "path.json").read_text(encoding="utf-8"))
    assert "configs" in payload
