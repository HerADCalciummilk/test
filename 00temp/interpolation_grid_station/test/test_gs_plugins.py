# -*- coding: utf-8 -*-
"""格点→站点插件烟雾 / 对照 ``utils.interpolating``。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for _p in (str(_SRC), str(_ROOT), str(_ROOT.parents[0])):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import meteva_base as meb
import numpy as np
import pandas as pd

from interp_gs_cubic_plugin import InterpGsCubic
from interp_gs_linear_plugin import InterpGsLinear
from interp_gs_nearest_plugin import InterpGsNearest


def _make_field():
    """简单线性场 f = lon + 0.1 * lat，便于核对插值。"""
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


def test_nearest_linear_cubic_smoke():
    grd, sta = _make_field()
    near = InterpGsNearest().process(grd, sta)
    lin = InterpGsLinear().process(grd, sta)
    cub = InterpGsCubic().process(grd, sta)
    assert near is not None and len(near) >= 1
    assert lin is not None and len(lin) >= 1
    assert cub is not None and len(cub) >= 1
    # 格点上的站点：线性应接近真值 lon+0.1*lat
    row = lin.loc[lin["id"] == 2].iloc[0]
    member = [c for c in lin.columns if c not in ("level", "time", "dtime", "id", "lon", "lat")][0]
    expect = 105.0 + 0.1 * 25.0
    assert abs(float(row[member]) - expect) < 1e-5


def test_match_interpolating_xy():
    from utils import interpolating as ref

    grd, sta = _make_field()
    member = list(grd["member"].values)[0]
    for Plugin, fn in (
        (InterpGsNearest, ref.interp_gs_nearest),
        (InterpGsLinear, ref.interp_gs_linear),
        (InterpGsCubic, ref.interp_gs_cubic),
    ):
        a = Plugin().process(grd.copy(deep=True), sta.copy())
        b = fn(grd.copy(deep=True), sta.copy())
        assert a is not None and b is not None
        a = a.sort_values("id").reset_index(drop=True)
        b = b.sort_values("id").reset_index(drop=True)
        np.testing.assert_allclose(
            a[member].astype(float).values,
            b[member].astype(float).values,
            rtol=1e-6,
            atol=1e-6,
        )


def _make_xydt_field():
    """矩形水平网（nlat!=nlon）+ 多时效线性场 f=lon+0.1*lat+0.01*dtime。

    原 interpolating xydt 在 nlat!=nlon 时会因 coords 维错误直接失败。
    """
    grid = meb.grid(
        [100, 104, 1.0],
        [20, 22, 1.0],
        gtime=["2020010100"],
        dtime_list=[0, 3, 6],
        level_list=[0],
        member_list=["data0"],
    )
    grd = meb.grid_data(grid)
    lon = grd["lon"].values
    lat = grd["lat"].values
    dts = grd["dtime"].values.astype(float)
    for k, dt in enumerate(dts):
        lon2d, lat2d = np.meshgrid(lon, lat)
        grd.values[0, 0, 0, k, :, :] = lon2d + 0.1 * lat2d + 0.01 * float(dt)
    sta = pd.DataFrame(
        {
            "level": [0, 0],
            "time": [pd.Timestamp("2020-01-01")] * 2,
            "dtime": [1.5, 3.0],
            "id": [1, 2],
            "lon": [100.5, 102.0],
            "lat": [20.5, 21.0],
            "data0": [np.nan, np.nan],
        }
    )
    return grd, sta


def test_xydt_linear_analytic():
    grd, sta = _make_xydt_field()
    out = InterpGsLinear(used_coords="xydt").process(grd, sta)
    assert out is not None
    out = out.sort_values("id").reset_index(drop=True)
    expect = out["lon"].values + 0.1 * out["lat"].values + 0.01 * out["dtime"].values
    np.testing.assert_allclose(out["data0"].astype(float).values, expect, atol=1e-6)


def test_xydt_rejects_single_dtime():
    grd, sta = _make_field()
    try:
        InterpGsLinear(used_coords="xydt").process(grd, sta)
    except ValueError as e:
        assert "dtime" in str(e)
    else:
        raise AssertionError("expected ValueError for single dtime")


if __name__ == "__main__":
    test_nearest_linear_cubic_smoke()
    test_match_interpolating_xy()
    test_xydt_linear_analytic()
    test_xydt_rejects_single_dtime()
    print("ok")
