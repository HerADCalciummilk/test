# -*- coding: utf-8 -*-
"""
扩大测试：Extrapolation + P1 再处理 vs Lagrangian。

统一模块 ``src/utils/project_align.py``

运行::
    python demo_advection_p1_compare.py
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
from frequency_matching_rain24_plugin import Lagrangian  # noqa: E402
from utils.project_align import extrapolate_like_lagrangian  # noqa: E402

import meteva.base as meb  # noqa: E402

DLON = DLAT = 0.1


def arr(g):
    return np.asarray(g.data if hasattr(g, "data") else g, dtype=float).squeeze()


def make_blob(lon0, lat0, amp=20.0, sig=0.35):
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon, lat = np.asarray(rain.lon), np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field = amp * np.exp(-((lon2d - lon0) ** 2 + (lat2d - lat0) ** 2) / sig ** 2)
    rain.data = [[[[field]]]]
    return rain, lon, lat


def make_two_blob():
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon, lat = np.asarray(rain.lon), np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field = (
        18 * np.exp(-((lon2d - 111.3) ** 2 + (lat2d - 34.2) ** 2) / 0.28 ** 2)
        + 16 * np.exp(-((lon2d - 112.7) ** 2 + (lat2d - 35.6) ** 2) / 0.28 ** 2)
    )
    rain.data = [[[[field]]]]
    return rain, lon, lat


def uv_const(rain, u_deg, v_deg):
    a = arr(rain)
    u, v = rain.copy(), rain.copy()
    u.data = [[[[np.full_like(a, u_deg)]]]]
    v.data = [[[[np.full_like(a, v_deg)]]]]
    return u, v


def uv_shear(rain, u0, v0):
    a = arr(rain)
    lat = np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(np.asarray(rain.lon), lat)
    w = (lat2d - lat.min()) / max(lat.max() - lat.min(), 1e-6)
    uu = u0 * (0.5 + w)
    vv = np.full_like(a, v0)
    u, v = rain.copy(), rain.copy()
    u.data = [[[[uu]]]]
    v.data = [[[[vv]]]]
    return u, v, uu, vv


def run_pair(rain, lon, lat, u, v, uu, vv):
    precip = arr(rain)
    out_l = arr(Lagrangian.simple_semi_lagrangian_in_angle(u, v, rain, 1.0))
    out_p1 = extrapolate_like_lagrangian(precip, uu, vv, lon, lat, DLON, DLAT)
    d = out_p1 - out_l
    return {
        "rain0": precip, "L": out_l, "P1": out_p1, "diff": d,
        "lon": lon, "lat": lat,
        "n_nan": 0,
        "meanAbs": float(np.mean(np.abs(d))),
        "maxAbs": float(np.max(np.abs(d))),
        "ok": float(np.max(np.abs(d))) < 1e-6,
    }


def main():
    cases = []

    # —— 边界 8 组 ——
    for name, lon0, lat0, ud, vd in [
        ("边界 西南东移0.3", 110.6, 33.6, 0.3, 0.0),
        ("边界 西南东移0.5", 110.6, 33.6, 0.5, 0.0),
        ("边界 西南东移1.0", 110.6, 33.6, 1.0, 0.0),
        ("边界 西缘东移0.3", 110.5, 35.0, 0.3, 0.0),
        ("边界 南缘北移0.3", 112.0, 33.5, 0.0, 0.3),
        ("边界 东南西移0.3", 113.4, 33.6, -0.3, 0.0),
        ("边界 西北南移0.3", 110.6, 36.4, 0.0, -0.3),
        ("边界 东北西南0.3", 113.4, 36.4, -0.3, -0.3),
    ]:
        rain, lon, lat = make_blob(lon0, lat0)
        u, v = uv_const(rain, ud, vd)
        uu = np.full_like(arr(rain), ud)
        vv = np.full_like(arr(rain), vd)
        cases.append((name, rain, lon, lat, u, v, uu, vv))

    # —— 域内 8 组 ——
    for name, lon0, lat0, ud, vd in [
        ("域内 中心东移0.3", 112.0, 35.0, 0.3, 0.0),
        ("域内 中心西移0.2", 112.0, 35.0, -0.2, 0.0),
        ("域内 中心北移0.2", 112.0, 35.0, 0.0, 0.2),
        ("域内 中心东北0.2", 112.0, 35.0, 0.2, 0.2),
        ("域内 中心南移0.4", 112.0, 35.0, 0.0, -0.4),
        ("域内 偏北东移0.3", 112.0, 35.5, 0.3, 0.0),
        ("域内 零位移", 112.0, 35.0, 0.0, 0.0),
        ("域内 东移0.8", 112.0, 35.0, 0.8, 0.0),
    ]:
        rain, lon, lat = make_blob(lon0, lat0)
        u, v = uv_const(rain, ud, vd)
        uu = np.full_like(arr(rain), ud)
        vv = np.full_like(arr(rain), vd)
        cases.append((name, rain, lon, lat, u, v, uu, vv))

    # —— 额外形态 ——
    rain, lon, lat = make_two_blob()
    u, v = uv_const(rain, 0.3, 0.0)
    uu = np.full_like(arr(rain), 0.3)
    vv = np.full_like(arr(rain), 0.0)
    cases.append(("域内 双斑东移0.3", rain, lon, lat, u, v, uu, vv))

    rain, lon, lat = make_blob(112.0, 35.0)
    u, v, uu, vv = uv_shear(rain, 0.3, 0.0)
    cases.append(("域内 切变UV", rain, lon, lat, u, v, uu, vv))

    rain, lon, lat = make_blob(110.6, 33.6)
    u, v, uu, vv = uv_shear(rain, 0.4, 0.1)
    cases.append(("边界 角落+切变", rain, lon, lat, u, v, uu, vv))

    print("=" * 70)
    print("扩大测试：project_align.extrapolate_like_lagrangian vs Lagrangian")
    print(f"模块: {os.path.join(RAIN_SRC, 'utils', 'project_align.py')}")
    print(f"{'用例':<22} {'nan':>5} {'meanAbs':>12} {'maxAbs':>12} {'一致':>6}")
    print("-" * 70)

    results = []
    for name, rain, lon, lat, u, v, uu, vv in cases:
        r = run_pair(rain, lon, lat, u, v, uu, vv)
        r["name"] = name
        results.append(r)
        print(
            f"{name:<22} {r['n_nan']:5d} {r['meanAbs']:12.2e} "
            f"{r['maxAbs']:12.2e} {'是' if r['ok'] else '否':>6}"
        )

    n_ok = sum(1 for r in results if r["ok"])
    print("-" * 70)
    print(f"完全一致: {n_ok}/{len(results)}")
    print("是 → P1 后再处理与 Lagrangian 数值相同（maxAbs<1e-6）")
    print("=" * 70)

    # 图：抽 3 边界 + 3 域内
    import matplotlib.pyplot as plt

    pick = [
        "边界 西南东移0.3", "边界 西缘东移0.3", "边界 东南西移0.3",
        "域内 中心东移0.3", "域内 中心东北0.2", "域内 双斑东移0.3",
    ]
    by_name = {r["name"]: r for r in results}
    fig, axes = plt.subplots(6, 4, figsize=(12, 14), constrained_layout=True)
    for row, name in enumerate(pick):
        r = by_name[name]
        vmax = max(r["rain0"].max(), r["L"].max(), r["P1"].max(), 1.0)
        dmax = max(r["maxAbs"], 1e-3)
        for col, (data, sub, cmap, vmin, vmax_) in enumerate([
            (r["rain0"], "输入", "Blues", 0, vmax),
            (r["L"], "Lagrangian", "Blues", 0, vmax),
            (r["P1"], "Extrap+P1", "Blues", 0, vmax),
            (r["diff"], f"差 max={r['maxAbs']:.0e}", "RdBu_r", -dmax, dmax),
        ]):
            ax = axes[row, col]
            im = ax.pcolormesh(
                r["lon"], r["lat"], data, shading="auto",
                cmap=cmap, vmin=vmin, vmax=vmax_,
            )
            if col == 0:
                ax.set_ylabel(name.replace(" ", "\n"), fontsize=8)
            if row == 0:
                ax.set_title(sub, fontsize=10)
            ax.set_aspect("equal")
            fig.colorbar(im, ax=ax, fraction=0.046)

    fig.suptitle(
        f"project_align 测试  一致 {n_ok}/{len(results)}",
        fontsize=12,
    )
    png = os.path.join(HERE, "demo_advection_p1_compare.png")
    fig.savefig(png, dpi=120)
    print(f"图: {png}")


if __name__ == "__main__":
    main()
