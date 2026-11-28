# -*- coding: utf-8 -*-
"""InterpGs 统一入口：分派与结果一致性。"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import meteva_base as meb

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _p in (str(_SRC), str(_ROOT), str(_ROOT.parents[0])):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from interp_gs_cubic_plugin import InterpGsCubic
from interp_gs_linear_plugin import InterpGsLinear
from interp_gs_nearest_plugin import InterpGsNearest
from interp_gs_plugin import InterpGs


def _make_field():
    grid = meb.grid([100, 110, 1.0], [20, 30, 1.0])
    grd = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(grd["lon"].values, grd["lat"].values)
    grd.values[0, 0, 0, 0, :, :] = lon2d + 0.1 * lat2d
    sta = pd.DataFrame(
        {
            "level": [0, 0],
            "time": [pd.Timestamp("2020-01-01")] * 2,
            "dtime": [0, 0],
            "id": [1, 2],
            "lon": [100.3, 105.0],
            "lat": [20.4, 25.0],
            "data0": [np.nan, np.nan],
        }
    )
    return grd, sta


def _member_col(sta) -> str:
    return [
        c
        for c in sta.columns
        if c not in ("level", "time", "dtime", "id", "lon", "lat")
    ][0]


def test_normalize_case_and_only_three_methods():
    assert InterpGs._normalize_method("Linear") == "linear"
    assert InterpGs._normalize_method("NEAREST") == "nearest"
    for bad in ("unknown", "bilinear", "idw", "interp_gs_linear"):
        with pytest.raises(ValueError, match="method"):
            InterpGs(method=bad)


def test_signature_lists_all_params():
    params = set(inspect.signature(InterpGs.__init__).parameters)
    assert {"method", "used_coords"} <= params


def test_unused_method_params_are_ignored():
    plugin = InterpGs(method="nearest", used_coords="xydt")
    assert plugin.method == "nearest"
    assert isinstance(plugin._impl, InterpGsNearest)


def test_each_method_matches_direct_plugin():
    grd, sta = _make_field()
    cases = [
        ("linear", InterpGsLinear(used_coords="xy"), {"used_coords": "xy"}),
        ("nearest", InterpGsNearest(), {}),
        ("cubic", InterpGsCubic(), {}),
    ]
    for method, direct, extra in cases:
        a = InterpGs(method=method, **extra).process(grd, sta)
        b = direct.process(grd, sta)
        assert a is not None and b is not None
        member = _member_col(a)
        a = a.sort_values("id").reset_index(drop=True)
        b = b.sort_values("id").reset_index(drop=True)
        np.testing.assert_allclose(
            a[member].astype(float).values,
            b[member].astype(float).values,
            rtol=1e-6,
            atol=1e-6,
        )


def test_used_coords_validation():
    with pytest.raises(ValueError, match="used_coords"):
        InterpGs(method="linear", used_coords="bad")


def test_exported_from_package():
    temp_root = str(Path(__file__).resolve().parents[2])
    if temp_root not in sys.path:
        sys.path.insert(0, temp_root)
    pkg = __import__("interpolation_grid_station.src", fromlist=["InterpGs", "__all__"])
    assert "InterpGs" in pkg.__all__
    assert pkg.InterpGs.__name__ == "InterpGs"
