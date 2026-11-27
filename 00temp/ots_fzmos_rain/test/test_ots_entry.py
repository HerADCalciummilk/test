# -*- coding: utf-8 -*-
"""入口参数和订正公式的轻量检查，不读业务数据。"""
import configparser
import inspect
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from _util_plugin import THRESHOLD_IN, combine_rain24, correct_precipitation
from cli.ots_fzmos_rain_cli import process


def test_conf_keys_are_process_parameters():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "resource" / "conf.ini", encoding="utf-8")
    keys = {key for key, _ in parser.items("process")}
    params = set(inspect.signature(process).parameters)
    missing = keys - params
    assert not missing, missing


def test_threshold_task_requires_paths():
    try:
        process(task="threshold", obs_dir="", ec_dir="", output_file="", station_file="")
    except ValueError as exc:
        assert "obs_dir" in str(exc)
        return
    raise AssertionError("缺少路径时应该报错")


def test_piecewise_ots_correction_and_missing_value():
    threshold_out = np.asarray(
        [0.2, 2.0, 6.0, 12.0, 24.0, 36.0, 48.0, 72.0, 96.0, 144.0],
        dtype=np.float32,
    )
    values = np.asarray([[0.1, 0.2, 4.0, 144.0, 288.0, 9999.0]], dtype=np.float32)
    result = correct_precipitation(values, threshold_out)
    assert result[0, 0] == 0.0
    assert result[0, 1] == THRESHOLD_IN[0]
    assert result[0, 2] == 3.0
    assert result[0, 3] == 150.0
    assert result[0, 4] == 300.0
    assert result[0, 5] == 9999.0


def test_adjacent_rain24_marks_overflow():
    current = np.asarray([[1000.0, 1.0]], dtype=np.float32)
    previous = np.asarray([[1001.0, 2.0]], dtype=np.float32)
    out = combine_rain24(current, previous)
    assert out[0, 0] == np.float32(9999.0)
    assert out[0, 1] == np.float32(3.0)
