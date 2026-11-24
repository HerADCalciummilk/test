# -*- coding: utf-8 -*-
"""新入口：CLI 经 DbTransPlugin 调度，无 _process / 多进程。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLI = os.path.join(_ROOT, "cli")
_SRC = os.path.join(_ROOT, "src")
for _p in (_CLI, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

import db_trans_cli as entry
from db_trans_plugin import DbTransPlugin


def test_cli_does_not_import_old_process():
    text = open(entry.__file__, encoding="utf-8").read()
    assert "import main" not in text
    assert "from main" not in text
    assert "resolve_args" not in text
    assert "SimpleParallelTool" not in text
    assert "def _process" not in text
    assert "DbTransPlugin" in text
    for name in ("get_resolved_paths", "set_main_ini", "set_call_overrides", "get_runtime_config"):
        assert name not in text


def test_summary_lists_methods(capsys):
    assert entry.process() == 0
    out = capsys.readouterr().out
    assert "db" in out
    assert entry.process.__nimm_submodule__ == "db_trans"


def test_explicit_db_transform():
    result = entry.process(method="db", values="0.1,1,10")
    assert result is not False
    np.testing.assert_allclose(np.asarray(result, dtype=float), [-10.0, 0.0, 10.0])


def test_plugin_db_direct():
    result, metadata = DbTransPlugin().process(
        [0.0, 0.05, 0.1, 1.0, 10.0, 100.0],
        method="db",
    )
    assert metadata["transform"] == "dB"
    np.testing.assert_allclose(result, [-15.0, -15.0, -10.0, 0.0, 10.0, 20.0])


def test_plugin_box_uses_kwargs_lambda():
    result, metadata = DbTransPlugin().process(
        [0.1, 1.0, 10.0],
        method="box",
        Lambda=0.0,
        threshold=0.1,
    )
    assert metadata["transform"] == "BoxCox"
    assert metadata["BoxCox_lambda"] == 0.0
    assert result is not None


def test_missing_values_raise():
    try:
        entry.process(method="db")
    except ValueError as exc:
        assert "values" in str(exc)
    else:
        raise AssertionError("db without values should raise")
