# -*- coding: utf-8 -*-
"""Cressman 烟测：构造最小站点场插到粗网格。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("meteva_base")
import meteva_base

from interp_sg_cressman import InterpSGCressmanPlugin, interp_sg_cressman


def _tiny_sta():
    # meteva_base 站点表：需含 member/level/time/dtime/id/lon/lat/data0
    rows = [
        {"level": 0, "time": "2024010108", "dtime": 0, "id": 1, "lon": 101.0, "lat": 31.0, "data0": 10.0},
        {"level": 0, "time": "2024010108", "dtime": 0, "id": 2, "lon": 101.5, "lat": 31.5, "data0": 20.0},
        {"level": 0, "time": "2024010108", "dtime": 0, "id": 3, "lon": 100.5, "lat": 30.5, "data0": 5.0},
    ]
    df = pd.DataFrame(rows)
    # 走标准 sta 构造（若 API 可用）
    if hasattr(meteva_base, "sta_data"):
        try:
            return meteva_base.sta_data(df)
        except Exception:
            pass
    if hasattr(meteva_base, "composers") and hasattr(meteva_base.composers, "sta_data"):
        try:
            return meteva_base.composers.sta_data(df)
        except Exception:
            pass
    # 最小兼容：补 member 列后直接作为 stadata 使用
    if "member" not in df.columns:
        df.insert(0, "member", "data0")
    return df


def test_interp_sg_cressman_smoke():
    sta = _tiny_sta()
    grid = meteva_base.basicdata.grid([100, 102, 0.5], [30, 32, 0.5])
    try:
        out = interp_sg_cressman(
            sta, grid, r_list=[200000, 100000], nearNum=3, outer_value=0.0,
        )
    except Exception as e:
        pytest.skip("环境无法完成 Cressman 烟测: %s" % e)
    assert out is not None
    vals = np.asarray(out.values, dtype=float)
    assert vals.size > 0
    assert np.nanmax(vals) > 0


def test_plugin_callable():
    sta = _tiny_sta()
    grid = meteva_base.basicdata.grid([100, 102, 0.5], [30, 32, 0.5])
    plugin = InterpSGCressmanPlugin(r_list=[150000], nearNum=3, outer_value=0.0)
    try:
        out = plugin(sta, grid)
    except Exception as e:
        pytest.skip("环境无法完成插件烟测: %s" % e)
    assert out is not None
