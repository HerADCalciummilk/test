# -*- coding: utf-8 -*-
"""
在「必须走项目核 + 封装再处理」约束下，验证/标定封装手段相对原版的误差。
原版仅作离线对照尺，业务不调用。

运行::
    python demo_cressman_project_tune.py
"""
from __future__ import annotations

import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]

from interpolation import GressManInterpolation
from utils.data_proc import creat_M3_grd
from utils.project_align import cressman_project_innov
import meteva.base as meb


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def make_case(nsta, seed):
    rng = np.random.default_rng(seed)
    lon0, lat0 = 110.0, 35.0
    half, dlon = 1.5, 0.1
    grid = meb.grid([lon0 - half, lon0 + half, dlon], [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    slon = lon0 + rng.uniform(-0.8, 0.8, nsta)
    slat = lat0 + rng.uniform(-0.8, 0.8, nsta)
    sval = 10.0 + rng.uniform(0, 15, nsta)
    sta = creat_M3_grd(list(slon), list(slat), list(sval), rpt="2024010108", dtime=0)
    return sta, bg, [0.8, 0.6, 0.4, 0.2]


def metrics(pred, ref):
    d = pred - ref
    return {
        "meanAbs": float(np.mean(np.abs(d))),
        "rmse": float(np.sqrt(np.mean(d * d))),
        "maxAbs": float(np.max(np.abs(d))),
        "corr": float(np.corrcoef(pred.ravel(), ref.ravel())[0, 1]),
    }


def eval_params(cases, **kw):
    scores = []
    for sta, bg, rs in cases:
        ref = arr(GressManInterpolation(sta, bg.copy(), rs, rain_limit=0.01))
        pred = arr(cressman_project_innov(sta, bg.copy(), rs, rain_limit=0.01, **kw))
        scores.append(metrics(pred, ref))
    return {k: float(np.mean([s[k] for s in scores])) for k in scores[0]}


def main():
    cases = [make_case(20, 20), make_case(50, 50), make_case(100, 100)]

    bare = eval_params(
        cases,
        r_km_scale=1.0,
        innov_gain=1.0,
        residual_passes=0,
        residual_degree_polish=False,
        degree_blend=0.0,
        station_anchor_strength=0.0,
    )
    print("=" * 72)
    print("仅项目核（无抛光无融合）:", bare)
    print("-" * 72)
    # 业务默认：项目仍占权重；blend 越大越贴原版
    best = None
    best_m = None
    for blend in (0.5, 0.65, 0.75, 0.85, 0.9, 0.95):
        for rounds in (0, 1):
            kw = dict(
                r_km_scale=1.35,
                innov_gain=1.0,
                residual_passes=0,
                residual_degree_polish=bool(rounds),
                residual_polish_rounds=max(rounds, 1),
                degree_blend=blend,
                station_anchor_strength=0.0,
                station_anchor_radius=0.35,
            )
            m = eval_params(cases, **kw)
            print(
                f"blend={blend:.2f} polish={bool(rounds)}  "
                f"meanAbs={m['meanAbs']:.4f} maxAbs={m['maxAbs']:.4f} corr={m['corr']:.6f}"
            )
            key = (m["meanAbs"], m["rmse"], m["maxAbs"])
            if best is None or key < best:
                best = key
                best_m = (kw, m)

    print("-" * 72)
    print("推荐封装参数（项目核仍参与）:", best_m[0])
    print("推荐指标:                    ", best_m[1])
    print(
        f"meanAbs  {bare['meanAbs']:.4f} → {best_m[1]['meanAbs']:.4f}  "
        f"({(1 - best_m[1]['meanAbs'] / max(bare['meanAbs'], 1e-9)) * 100:.1f}%↓)"
    )
    print(
        f"maxAbs   {bare['maxAbs']:.4f} → {best_m[1]['maxAbs']:.4f}  "
        f"({(1 - best_m[1]['maxAbs'] / max(bare['maxAbs'], 1e-9)) * 100:.1f}%↓)"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
