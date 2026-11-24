# -*- coding: utf-8 -*-
"""权重、起报时次与配置解析。不读取模式降水。"""
import datetime
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pre_fcst_tch_realtime import (
    build_title,
    detect_grid_format,
    model_grid_path,
    model_m4_path,
    normalize_ipt_type,
    select_initial_time,
)
from tch_weight_plugin import TchWeightPlugin
from utils.util_env import resolve_process_args, set_main_ini


def test_weight_inverse_to_error():
    w = TchWeightPlugin().get_weight_mul(np.array([1.0, 2.0]))
    assert np.isclose(w.sum(), 1.0)
    assert np.isclose(w[0], 0.8)
    assert np.isclose(w[1], 0.2)


def test_equal_error_equal_weight():
    w = TchWeightPlugin().get_weight_mul(np.array([3.0, 3.0, 3.0]))
    assert np.allclose(w, [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])


def test_select_initial_time_afternoon_is_today_00():
    now = datetime.datetime(2024, 6, 4, 15, 0, 0)
    assert select_initial_time(now, 12, 0, 12) == datetime.datetime(2024, 6, 4, 0, 0)


def test_select_initial_time_morning_is_previous_day_12():
    now = datetime.datetime(2024, 6, 4, 4, 0, 0)
    assert select_initial_time(now, 12, 0, 12) == datetime.datetime(2024, 6, 3, 12, 0)


def test_model_path_does_not_rewrite_nimm():
    path = model_m4_path(
        r"D:\Work\NIMM_pip_testdata\multi_rain_mait24_blending\test_data\\",
        "ecmwf",
        datetime.datetime(2026, 5, 23, 12, 0),
        36,
    )
    assert "NIMM_pip_testdata" in path
    assert "NI05_pip_testdata" not in path
    assert path.replace("\\", "/").endswith("ecmwf/sfc/20260523/2026052312.036.m4")


def test_model_grid_path_defaults_to_nc():
    path = model_grid_path(
        r"D:\Work\NIMM_pip_testdata\multi_rain_mait24_blending\test_data\\",
        "ecmwf",
        datetime.datetime(2026, 5, 23, 12, 0),
        36,
        ipt_type="nc",
    )
    assert path.replace("\\", "/").endswith("ecmwf/sfc/20260523/2026052312.036.nc")


def test_detect_grid_format_by_suffix():
    assert normalize_ipt_type(None) == "nc"
    assert normalize_ipt_type("NetCDF") == "nc"
    assert detect_grid_format(r"D:\a\b\2026052312.036.nc") == "nc"
    assert detect_grid_format(r"D:\a\b\2026052312.036.m4") == "m4"


def test_build_title():
    title = build_title("2024-06-04 08:00:00 AM", "08", 36, "TCH")
    assert title == "2024年06月04日08时36h时效24小时降水预报场(TCH)"


def test_resolve_uses_ini_and_explicit_wins():
    set_main_ini(None)
    cfg = resolve_process_args()
    assert cfg["fcst_hours"] == [36, 60, 84]
    assert cfg["model_list"][0] == "ecmwf"
    assert cfg["ipt_type"] == "nc"
    overridden = resolve_process_args(
        fcst_hours=[36], model_list=["ecmwf"], initial_time="20260523120000", ipt_type="m4"
    )
    assert overridden["fcst_hours"] == [36]
    assert overridden["model_list"] == ["ecmwf"]
    assert overridden["initial_time"] == "20260523120000"
    assert overridden["station_level"] == 600
    assert overridden["ipt_type"] == "m4"
