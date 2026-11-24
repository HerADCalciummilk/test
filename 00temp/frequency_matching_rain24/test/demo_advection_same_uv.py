# -*- coding: utf-8 -*-
"""
多组 UV / 雨场：Lagrangian（度）vs Extrapolation（像素）是否每次一样。

换算：u_像素 = u_度/dlon，v_像素 = v_度/dlat；Extrapolation 出界 nan→0 再比。

运行::
    python demo_advection_same_uv.py
"""
from __future__ import annotations

import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
OF_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "optical_flow_nowcast"))

sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]
from frequency_matching_rain24_plugin import Lagrangian  # noqa: E402

sys.path.insert(0, OF_ROOT)
from src.extrapolation_plugin import forecast as extrap_forecast  # noqa: E402

import meteva.base as meb  # noqa: E402

DLON = DLAT = 0.1


def arr(g):
    return np.asarray(g.data if hasattr(g, "data") else g, dtype=float).squeeze()


def make_rain(kind: str):
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon = np.asarray(rain.lon)
    lat = np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    if kind == "gauss":
        field = 20.0 * np.exp(-((lon2d - 112.0) ** 2 + (lat2d - 35.0) ** 2) / 0.4 ** 2)
    elif kind == "gauss_off":
        # 偏到角落，更容易碰到出界
        field = 20.0 * np.exp(-((lon2d - 110.6) ** 2 + (lat2d - 33.6) ** 2) / 0.35 ** 2)
    elif kind == "two_blob":
        field = (
            18.0 * np.exp(-((lon2d - 111.5) ** 2 + (lat2d - 34.5) ** 2) / 0.3 ** 2)
            + 15.0 * np.exp(-((lon2d - 112.8) ** 2 + (lat2d - 35.5) ** 2) / 0.3 ** 2)
        )
    else:
        raise ValueError(kind)
    rain.data = [[[[field]]]]
    return rain


def make_uv_fields(rain, u_deg, v_deg, mode="uniform"):
    """mode=uniform 全场常数；shear 东西向随纬度变化。"""
    base = arr(rain)
    lat = np.asarray(rain.lat)
    lon = np.asarray(rain.lon)
    lon2d, lat2d = np.meshgrid(lon, lat)
    if mode == "uniform":
        uu = np.full_like(base, u_deg)
        vv = np.full_like(base, v_deg)
    else:  # shear
        # 北侧东移更大
        w = (lat2d - lat.min()) / max(lat.max() - lat.min(), 1e-6)
        uu = u_deg * (0.5 + w)
        vv = np.full_like(base, v_deg)
    u = rain.copy()
    v = rain.copy()
    u.data = [[[[uu]]]]
    v.data = [[[[vv]]]]
    return u, v, uu, vv


def run_one(name, rain_kind, u_deg, v_deg, uv_mode="uniform"):
    rain = make_rain(rain_kind)
    u, v, uu, vv = make_uv_fields(rain, u_deg, v_deg, mode=uv_mode)

    out_l = arr(Lagrangian.simple_semi_lagrangian_in_angle(u, v, rain, 1.0))

    precip = arr(rain)
    vel = np.stack([uu / DLON, vv / DLAT], axis=0)
    out_e = np.asarray(
        extrap_forecast(precip, vel, timesteps=1, extrap_method="semilagrangian")[0],
        dtype=float,
    )
    n_nan = int(np.sum(~np.isfinite(out_e)))
    out_e_fill = np.where(np.isfinite(out_e), out_e, 0.0)

    d = out_e_fill - out_l
    mean_abs = float(np.mean(np.abs(d)))
    rmse = float(np.sqrt(np.mean(d * d)))
    max_abs = float(np.max(np.abs(d)))
    same = max_abs < 1e-6
    return {
        "name": name,
        "u_deg": u_deg,
        "v_deg": v_deg,
        "u_px": u_deg / DLON,
        "v_px": v_deg / DLAT,
        "n_nan": n_nan,
        "meanAbs": mean_abs,
        "rmse": rmse,
        "maxAbs": max_abs,
        "same": same,
    }


def main():
    cases = [
        ("东移0.3° 单斑", "gauss", 0.3, 0.0, "uniform"),
        ("西移0.2° 单斑", "gauss", -0.2, 0.0, "uniform"),
        ("北移0.2° 单斑", "gauss", 0.0, 0.2, "uniform"),
        ("东北0.2/0.2 单斑", "gauss", 0.2, 0.2, "uniform"),
        ("东移0.5° 单斑", "gauss", 0.5, 0.0, "uniform"),
        ("东移0.3° 双斑", "two_blob", 0.3, 0.0, "uniform"),
        ("东移0.3° 角落斑", "gauss_off", 0.3, 0.0, "uniform"),
        ("大位移1.0° 单斑", "gauss", 1.0, 0.0, "uniform"),
        ("切变UV 东移", "gauss", 0.3, 0.0, "shear"),
        ("零位移", "gauss", 0.0, 0.0, "uniform"),
    ]

    print("=" * 78)
    print("多组测试：同 UV（度↔像素换算）Lagrangian vs Extrapolation")
    print(f"{'用例':<18} {'u°':>5} {'v°':>5} {'nan格':>6} "
          f"{'meanAbs':>10} {'maxAbs':>10} {'完全一致':>8}")
    print("-" * 78)

    results = []
    for name, kind, ud, vd, mode in cases:
        r = run_one(name, kind, ud, vd, uv_mode=mode)
        results.append(r)
        print(
            f"{r['name']:<18} {r['u_deg']:5.2f} {r['v_deg']:5.2f} {r['n_nan']:6d} "
            f"{r['meanAbs']:10.4f} {r['maxAbs']:10.4f} "
            f"{'是' if r['same'] else '否':>8}"
        )

    n_ok = sum(1 for r in results if r["same"])
    print("-" * 78)
    print(f"完全一致: {n_ok}/{len(results)}")
    if n_ok == len(results):
        print("结论：本组用例在「换算正确 + nan→0」后，结果每次都一样。")
    else:
        print("结论：并非每次都一样。不一致用例：")
        for r in results:
            if not r["same"]:
                print(f"  - {r['name']}: maxAbs={r['maxAbs']:.4f}, "
                      f"Extrapolation出界nan格={r['n_nan']}")
        print("常见原因：大位移/靠边雨斑 → Extrapolation 出界 nan，"
              "Lagrangian 用边界夹取，填 0 后仍可能对不齐。")
    print("=" * 78)


if __name__ == "__main__":
    main()
