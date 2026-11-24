# -*- coding: utf-8 -*-
"""CLI：reprocess 开关。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_ROOT, "cli")
if _CLI not in sys.path:
    sys.path.insert(0, _CLI)

import interp_sg_cressman_cli as entry


def test_cli_does_not_import_old_main():
    text = open(entry.__file__, encoding="utf-8").read()
    assert "import main" not in text
    assert "from main" not in text
    assert "from runner import process" not in text
    assert "import runner" not in text


def test_process_default_km(monkeypatch):
    seen = {}

    class FakePlugin:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def process(self, sta, grid=None, background=None):
            seen["sta"] = sta
            seen["grid"] = grid
            seen["background"] = background
            return "grd"

    monkeypatch.setattr(entry, "InterpSgCressman", FakePlugin)
    monkeypatch.setattr(entry, "_read_sta", lambda *a, **k: "STA")
    monkeypatch.setattr(entry, "_resolve_target_grid", lambda *a, **k: "GRID")
    monkeypatch.setattr(entry.meb, "write_griddata_to_micaps4", lambda *a, **k: None)

    entry.process(sta_path="a.m3", glon="70,140,0.1", glat="0,60,0.1")

    assert seen["sta"] == "STA"
    assert seen["grid"] == "GRID"
    assert seen["init"]["reprocess"] is False
    assert seen["init"]["r_list"] == [60000.0, 40000.0, 20000.0]
    assert entry.process.__nimm_submodule__ == "interp_sg_cressman"


def test_process_reprocess_true(monkeypatch):
    seen = {}

    class FakePlugin:
        def __init__(self, **kwargs):
            seen["init"] = kwargs

        def process(self, sta, grid=None, background=None):
            seen["background"] = background
            return "grd"

    monkeypatch.setattr(entry, "InterpSgCressman", FakePlugin)
    monkeypatch.setattr(entry, "_read_sta", lambda *a, **k: "STA")
    monkeypatch.setattr(entry, "_read_griddata", lambda *a, **k: "BG")
    monkeypatch.setattr(entry.meb, "write_griddata_to_micaps4", lambda *a, **k: None)

    entry.process(sta_path="a.m3", background_path="b.m4", reprocess=True)

    assert seen["init"]["reprocess"] is True
    assert seen["background"] == "BG"
    assert seen["init"]["r_list"] == [1.0, 0.8, 0.6, 0.4]


def test_reprocess_requires_background(monkeypatch):
    monkeypatch.setattr(entry, "_read_sta", lambda *a, **k: "STA")
    try:
        entry.process(sta_path="a.m3", reprocess=True)
    except ValueError as exc:
        assert "background" in str(exc).lower() or "reprocess" in str(exc).lower()
    else:
        raise AssertionError("reprocess without background should raise")


def test_missing_sta_raises():
    try:
        entry.process()
    except ValueError as exc:
        assert "sta_path" in str(exc)
    else:
        raise AssertionError("empty sta should raise")
