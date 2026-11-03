# -*- coding: utf-8 -*-
"""插值和光流分开测。每次只打印一块降水输入，以及原用法、项目用法各一份降水输出。

    python test/test_apply_interp_optical_flow.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd
import meteva.base as meb

from cal_optical_flow import Lagrangian as LagOld
from cal_optical_flow import OpticalFlow as FlowOld
from cal_optical_flow_nowcast import Lagrangian as LagNew
from cal_optical_flow_nowcast import OpticalFlow as FlowNew
from correct_tp_24h_nowcast import clip_slice_neighborhood
from interpolation import GressManInterpolation as cressman_old
from interpolation import bilinear_interp as bilinear_old
from interpolation import mesh_val as mesh_old
from interpolation_gg_linear import bilinear_interp as bilinear_new
from interpolation_gg_linear import mesh_val as mesh_new
from interpolation_sg_cressman import GressManInterpolation as cressman_new
from utils.data_proc import creat_M3_grd


def _grid(values, slon, slat, res):
    arr = np.asarray(values, dtype=float)
    nlat, nlon = arr.shape
    grid = meb.grid([slon, slon + res * (nlon - 1), res], [slat, slat + res * (nlat - 1), res])
    return meb.grid_data(grid, arr.reshape(1, 1, 1, 1, nlat, nlon))


def _show(title, arr):
    print()
    print(title)
    text = np.array2string(np.asarray(arr, dtype=float).squeeze(), precision=1, suppress_small=True)
    print(text)


def test_mesh_val():
    values = np.array(
        [
            [0, 2, 4, 6],
            [1, 3, 5, 7],
            [2, 4, 6, 8],
            [3, 5, 7, 9],
        ],
        dtype=float,
    )
    grd = _grid(values, slon=100, slat=30, res=1.0)
    old = np.asarray(mesh_old(grd, [100, 103, 30, 33, 1.0]).values).squeeze()
    new = np.asarray(mesh_new(grd, [100, 103, 30, 33, 1.0]).values).squeeze()
    print("\n【线性插值，格点到格点】原和项目结果相同")
    _show("输入", values)
    _show("原", old)
    _show("项目", new)
    assert old.shape == new.shape
    assert np.allclose(old, new)


def test_bilinear_interp():
    values = np.array([[10, 20], [30, 40]], dtype=float)
    grd = _grid(values, slon=100, slat=30, res=1.0)
    sta = pd.DataFrame({"id": [1, 2], "lon": [100.5, 120.0], "lat": [30.5, 50.0], "data0": [0.0, 0.0]})
    old = bilinear_old(grd, sta, dbUndef=0.0)["data0"].to_numpy()
    new = bilinear_new(grd, sta, dbUndef=0.0)["data0"].to_numpy()
    print("\n【线性插值，格点到站点】原和项目都是 25 和 0")
    _show("输入", values)
    _show("原", old)
    _show("项目", new)
    assert np.allclose(old, new)
    assert old[1] == 0.0


def test_cressman():
    values = np.ones((5, 5))
    grd = _grid(values, slon=100, slat=30, res=1.0)
    sta = creat_M3_grd([102.0], [32.0], [10.0])
    radii = [1.0, 0.8, 0.6, 0.4]
    extend = [100.0, 104.0, 30.0, 34.0]

    old = np.asarray(mesh_old(cressman_old(sta, grd, radii, rain_limit=0.01), extend + [1.0]).values).squeeze()
    sta_clip, grd_clip = clip_slice_neighborhood(sta, grd, extend, max(radii), mesh_new)
    new = np.asarray(mesh_new(cressman_new(sta_clip, grd_clip, radii, rain_limit=0.01), extend + [1.0]).values).squeeze()

    print("\n【Cressman，站点到格点】原结果中心升高，项目结果整片接近同一个数")
    _show("输入", values)
    _show("原", old)
    _show("项目", new)
    assert old.shape == new.shape
    assert np.isfinite(old).all() and np.isfinite(new).all()


def test_optical_flow():
    res = 0.25
    lon = np.arange(100, 108 + 1e-6, res)
    lat = np.arange(30, 38 + 1e-6, res)
    xx, yy = np.meshgrid(lon, lat)
    values = 40.0 * np.exp(-((xx - 103.5) ** 2 + (yy - 33.5) ** 2) / 4.0)
    after_arr = 40.0 * np.exp(-((xx - 104.5) ** 2 + (yy - 34.0) ** 2) / 4.0)
    before = _grid(values, slon=100, slat=30, res=res)
    after = _grid(after_arr, slon=100, slat=30, res=res)
    zero = before * 0

    old_flow = [zero.copy(), zero.copy()]
    FlowOld.get_optical_flow([before], [after], [[5.0, 5.0]], old_flow, rain_limit=25, num_limit=50)
    old_rain = np.asarray(
        LagOld.simple_semi_lagrangian_in_angle(old_flow[0], old_flow[1], before, 1.0).values
    ).squeeze()

    new_flow = [zero.copy(), zero.copy()]
    FlowNew.get_optical_flow([before], [after], [[5.0, 5.0]], new_flow, rain_limit=25, num_limit=50)
    new_rain = np.asarray(
        LagNew.simple_semi_lagrangian_in_angle(new_flow[0], new_flow[1], before, 1.0).values
    ).squeeze()

    center = (slice(12, 17), slice(12, 17))
    print("\n【光流】只看降水中心 5 格。原和项目都把雨区往东南移了一点")
    _show("输入", values[center])
    _show("原", old_rain[center])
    _show("项目", new_rain[center])
    assert old_rain.shape == new_rain.shape
    assert np.isfinite(old_rain).all()


