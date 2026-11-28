# -*- coding: utf-8 -*-
"""
验证：封装内复刻 GressMan vs 原版 GressMan vs 项目核 innov。

期望：reimpl 与原版 meanAbs ≈ 0；project 仍有残差。

运行::
    python demo_cressman_reimpl_vs_gressman.py
"""
from __future__ import annotations

import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
TEMP = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [RAIN_SRC, os.path.join(TEMP, "interpolation_station_grid", "src"), TEMP]
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils"), os.path.join(TEMP, "utils")]

from interp_sg_plugin import InterpSg
from utils.data_proc import creat_M3_grd
import meteva.base as meb


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def score(tag, pred, ref):
    d = pred - ref
    return (f"{tag:22s}  meanAbs={np.mean(np.abs(d)):.6e}  "
            f"rmse={np.sqrt(np.mean(d*d)):.6e}  maxAbs={np.max(np.abs(d)):.6e}")


def make_case(nsta=1, seed=0):
    rng = np.random.default_rng(seed)
    lon0, lat0 = 110.0, 35.0
    half, dlon = 1.5, 0.1
    grid = meb.grid([lon0 - half, lon0 + half, dlon], [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    if nsta == 1:
        slon, slat, sval = [lon0], [lat0], [20.0]
    else:
        slon = lon0 + rng.uniform(-0.8, 0.8, nsta)
        slat = lat0 + rng.uniform(-0.8, 0.8, nsta)
        sval = 10.0 + rng.uniform(0, 15, nsta)
    sta = creat_M3_grd(list(slon), list(slat), list(sval), rpt="2024010108", dtime=0)
    return sta, bg, [0.8, 0.6, 0.4, 0.2]


def main():
    print("=" * 72)
    print("Cressman：原版 GressMan vs 封装复刻 vs 项目核 innov")
    print("=" * 72)
    for nsta in (1, 20, 100):
        sta, bg, rs = make_case(nsta=nsta, seed=nsta)
        a = arr(
            InterpSg(
                method="cressman", r_list=rs, reprocess=True, rain_limit=0.01, degree_blend=1.0
            ).process(sta, background=bg.copy())
        )
        b = arr(
            InterpSg(
                method="cressman", r_list=rs, reprocess=True, rain_limit=0.01, degree_blend=1.0
            ).process(sta, background=bg.copy())
        )
        c = arr(
            InterpSg(
                method="cressman", r_list=rs, reprocess=True, rain_limit=0.01, degree_blend=0.85
            ).process(sta, background=bg.copy())
        )
        print(f"\n--- nsta={nsta} ---")
        print(" ", score("封装复刻 vs 原版", b, a))
        print(" ", score("项目innov vs 原版", c, a))
    print("=" * 72)
    print("结论：业务应用 cressman_innov_gressman_like（复刻）；项目核路径仅作对照。")


if __name__ == "__main__":
    main()
