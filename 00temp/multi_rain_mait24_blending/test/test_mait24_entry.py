# -*- coding: utf-8 -*-
"""新入口只调度，不跑完整集成。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_ROOT, "cli")
if _CLI not in sys.path:
    sys.path.insert(0, _CLI)

import multi_rain_mait24_blending_cli as entry


def test_cli_does_not_import_old_main():
    text = open(entry.__file__, encoding="utf-8").read()
    assert "import mait_24h" not in text
    assert "from mait_24h" not in text


def test_process_reads_required_keys_from_ini(monkeypatch):
    seen = {}

    def fake_multi(cls, params, pro_count, run):
        seen["params"] = params
        seen["pro_count"] = pro_count
        seen["run"] = run

    monkeypatch.setattr(entry.Mait24h, "process_multi", classmethod(fake_multi))
    entry.Mait24h.process()

    times = [item["time_input"] for item in seen["params"]]
    assert times == ["202401010800", "202401011200"]
    assert seen["pro_count"] == 4
    assert seen["run"]["para_path"].endswith("para_24.ini")
    assert seen["run"]["predict_valid_list"][0] == 36
    assert seen["run"]["is_obs_bjt"] is True
    assert "is_multi" not in seen["run"]
    assert entry.Mait24h.process.__func__.__nimm_submodule__ == "multi_rain_mait24_blending"
