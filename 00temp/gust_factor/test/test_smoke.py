# -*- coding: utf-8 -*-
"""烟测：系数计算 +（有样例 NC 时）订正。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[1]


def test_calc_factor_from_test_csv(tmp_path):
    pytest.importorskip("meteva_base")
    from gust_factor import GustFactorCalculatorPlugin, load_station_csv_dir

    csv_dir = _ROOT / "resource" / "test_data"
    if not csv_dir.is_dir() or not any(csv_dir.glob("*.csv")):
        pytest.skip("无 resource/test_data CSV")

    df = load_station_csv_dir(str(csv_dir))
    out_json = tmp_path / "gust_factor.json"
    g = GustFactorCalculatorPlugin().process(
        df, fore_hours=(24, 48, 72), save_path=str(out_json)
    )
    assert "24" in g and "param" in g["24"]
    assert out_json.is_file()
    assert g["24"]["param"] > 0


def test_correct_if_sample_nc(tmp_path):
    pytest.importorskip("meteva_base")
    from gust_factor import (
        GustCorrectWithFactorPlugin,
        GustFactorCalculatorPlugin,
        load_station_csv_dir,
        read_grid_nc,
        write_grid_nc,
    )

    sample = _ROOT / "resource" / "sample"
    u = sample / "UTC_20260505000000_WIU10_024.nc"
    v = sample / "UTC_20260505000000_WIV10_024.nc"
    csv_dir = _ROOT / "resource" / "test_data"
    if not u.is_file() or not v.is_file():
        pytest.skip("无 sample U/V NC")
    if not any(csv_dir.glob("*.csv")):
        pytest.skip("无 test_data CSV")

    factor_path = tmp_path / "gf.json"
    GustFactorCalculatorPlugin().process(
        load_station_csv_dir(str(csv_dir)),
        fore_hours=(24,),
        save_path=str(factor_path),
    )
    u_da = read_grid_nc(str(u))
    v_da = read_grid_nc(str(v))
    g_da = GustCorrectWithFactorPlugin().process(u_da, v_da, 24, str(factor_path))
    out = tmp_path / "gust.nc"
    write_grid_nc(g_da, str(out))
    assert out.is_file()
    arr = np.asarray(g_da.values)
    assert np.isfinite(arr).any()


def test_least_squares_degenerate():
    from gust_factor import GustFactorCalculatorPlugin

    plug = GustFactorCalculatorPlugin()
    a, b = plug._least_squares_method([1.0, 1.0, 1.0], [2.0, 2.0, 2.0])
    assert a == 1.0
    assert abs(b - 1.0) < 1e-9
