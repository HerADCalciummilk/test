# -*- coding: utf-8 -*-
"""新入口只调度，不跑完整集成。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_ROOT, "cli")
if _CLI not in sys.path:
    sys.path.insert(0, _CLI)

import multi_rain_mait01_blending_cli as entry


def test_cli_does_not_import_old_main():
    text = open(entry.__file__, encoding="utf-8").read()
    assert "import mait_1h" not in text
    assert "from mait_1h" not in text


def test_process_reads_required_keys_from_ini(monkeypatch):
    seen = {}

    class FakeTool:
        def __init__(self, target_func, parallel_mode, with_return, num_process, fixed_params):
            seen["target"] = target_func
            seen["pro_count"] = num_process
            seen["run"] = fixed_params

        def process(self, tasks):
            seen["tasks"] = tasks

    monkeypatch.setattr(entry, "SimpleParallelTool", FakeTool)
    entry.process()

    assert seen["tasks"]["time_input"] == ["202401010800", "202401011200"]
    assert seen["target"] is entry._process
    assert seen["pro_count"] == 4
    assert seen["run"]["para_path"].endswith("para_1.ini")
    assert seen["run"]["predict_valid_list"][0] == 1
    assert seen["run"]["is_obs_bjt"] is True
    assert "is_multi" not in seen["run"]
    assert entry.process.__nimm_submodule__ == "multi_rain_mait01_blending"
