# -*- coding: utf-8 -*-
"""新入口只调度一个起报循环，不跑订正。"""
import os
import sys
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_ROOT, "cli")
if _CLI not in sys.path:
    sys.path.insert(0, _CLI)

import frequency_matching_rain01_cli as entry


def test_process_reads_cycles_from_ini(monkeypatch):
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

    when = datetime.strptime("202604081130", "%Y%m%d%H%M")
    expect = [when - timedelta(hours=hour + 8) for hour in range(25)]
    assert seen["tasks"]["dt_input1"] == expect
    assert seen["target"] is entry._process
    assert seen["pro_count"] == 4
    assert seen["run"]["data_key"] == "ecmwf"
    assert seen["run"]["path_json"].endswith("path.json")
    assert seen["run"]["valid_workers"] == 1
    assert "is_multi" not in seen["run"]
    assert entry.process.__nimm_submodule__ == "frequency_matching_rain01"


def test_entry_does_not_read_ini_or_relaunch():
    text = open(entry.__file__, encoding="utf-8").read()
    assert "get_resolved_paths" not in text
    assert "set_main_ini" not in text
    assert "set_call_overrides" not in text
    assert "subprocess" not in text
    for line in text.splitlines():
        stripped = line.strip()
        assert not stripped.startswith("from runner import process")
        assert not stripped.startswith("import runner")
