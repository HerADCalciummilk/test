# -*- coding: utf-8 -*-
"""频率匹配与工具函数单元测试。"""
import numpy as np

from utils.types import GridData
from proc import FrequencyMatch
from utils.string_process import date_replace
from datetime import datetime


def test_date_replace_tokens():
    dt = datetime(2026, 4, 8, 11, 30)
    out = date_replace("YYYYMMDDHH_VVV", dt, 12)
    assert out == "2026040811_012"


def test_frequency_match_correct_model_data():
    grid = GridData(0.0, 1.0, 0.0, 1.0, 1.0, 1.0)
    grid.val[:] = 2.0
    fact_level = np.array([0.0, 10.0], dtype=float)
    model_level = np.array([0.0, 5.0], dtype=float)
    out = FrequencyMatch.correct_model_data(grid, fact_level, model_level)
    assert np.allclose(out.val, 4.0)


def test_get_used_model_level_empty():
    ml, fu = FrequencyMatch.get_used_model_level([], [], [0.1, 1.0])
    assert len(ml) == 0
    assert len(fu) == 0
