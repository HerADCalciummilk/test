# -*- coding: utf-8 -*-
"""
扩大测试：域内 / 边界 / 切变 — Extrapolation(n_iter=0)+P1 vs Lagrangian。
通过则确认可使用 ``utils.cressman_extrap_reprocess.extrapolate_like_lagrangian``。

运行::
    python demo_advection_niter0_p1.py
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
from utils.cressman_extrap_reprocess import extrapolate_like_lagrangian  # noqa: E402

import meteva.base as meb  # noqa: E402

DLON = DLAT = 0.1
TOL = 1e-6


def arr(g):
    return np.asarray(g.data if hasattr(g, "data") else g, dtype=float).squeeze()


def make_blob(lon0, lat0, amp=20.0, sig=0.35):
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon, lat = np.asarray(rain.lon), np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field = amp * np.exp(-((lon2d - lon0) ** 2 + (lat2d - lat0) ** 2) / sig ** 2)
    rain.data = [[[[field]]]]
    return rain, lon, lat, field


def make_two_blob():
    grid = meb.grid([110.0, 114.0, DLON], [33.0, 37.0, DLAT])
    rain = meb.grid_data(grid)
    lon, lat = np.asarray(rain.lon), np.asarray(rain.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field = (
        18 * np.exp(-((lon2d - 111.2) ** 2 + (lat2d - 34.0) ** 2) / 0.25 ** 2)
        + 16 * np.exp(-((lon2d - 112.8) ** 2 + (lat2d - 35.8) ** 2) / 0.25 ** 2)
        + 12 * np.exp(-((lon2d - 112.0) ** 2 + (lat2d - 35.0) ** 2) / 0.5 ** 2)
    )
    rain.data = [[[[field]]]]
    return rain, lon, lat, field


def uv_uniform(shape, ud, vd):
    return np.full(shape, ud, float), np.full(shape, vd, float)


def uv_shear_lat(lon, lat, u0, v0):
    _, lat2d = np.meshgrid(lon, lat)
    w = (lat2d - lat.min()) / max(lat.max() - lat.min(), 1e-6)
    return u0 * (0.5 + w), np.full_like(lat2d, v0, float)


def uv_shear_lon(lon, lat, u0, v0):
    lon2d, _ = np.meshgrid(lon, lat)
    w = (lon2d - lon.min()) / max(lon.max() - lon.min(), 1e-6)
    return np.full_like(lon2d, u0, float), v0 * (0.5 + w)


def uv_shear_both(lon, lat, u0, v0):
    lon2d, lat2d = np.meshgrid(lon, lat)
    wx = (lon2d - lon.min()) / max(lon.max() - lon.min(), 1e-6)
    wy = (lat2d - lat.min()) / max(lat.max() - lat.min(), 1e-6)
    return u0 * (0.3 + wx), v0 * (0.3 + wy)


def run_one(name, rain, lon, lat, field, uu, vv):
    u, v = rain.copy(), rain.copy()
    u.data = [[[[uu]]]]
    v.data = [[[[vv]]]]
    out_l = arr(Lagrangian.simple_semi_lagrangian_in_angle(u, v, rain, 1.0))
    out_a = extrapolate_like_lagrangian(
        field, uu, vv, lon, lat, DLON, DLAT, delta_time=1.0,
    )
    d = out_a - out_l
    return {
        "name": name,
        "maxAbs": float(np.max(np.abs(d))),
        "meanAbs": float(np.mean(np.abs(d))),
        "ok": float(np.max(np.abs(d))) < TOL,
        "L": out_l,
        "A": out_a,
        "diff": d,
        "rain0": field,
        "lon": lon,
        "lat": lat,
    }


def build_cases():
    cases = []

    # —— 域内 · 均匀 ——
    for title, ud, vd in [
        ("域内均匀 东0.1", 0.1, 0.0),
        ("域内均匀 东0.3", 0.3, 0.0),
        ("域内均匀 东0.8", 0.8, 0.0),
        ("域内均匀 西0.5", -0.5, 0.0),
        ("域内均匀 北0.4", 0.0, 0.4),
        ("域内均匀 南0.3", 0.0, -0.3),
        ("域内均匀 东北0.25", 0.25, 0.25),
        ("域内均匀 西南0.35", -0.35, -0.35),
        ("域内均匀 零", 0.0, 0.0),
    ]:
        rain, lon, lat, f = make_blob(112.0, 35.0)
        uu, vv = uv_uniform(f.shape, ud, vd)
        cases.append((title, rain, lon, lat, f, uu, vv))

    # —— 边界 · 均匀 ——
    for title, lon0, lat0, ud, vd in [
        ("边界均匀 西南东0.3", 110.6, 33.6, 0.3, 0.0),
        ("边界均匀 西南东1.0", 110.6, 33.6, 1.0, 0.0),
        ("边界均匀 西南北0.4", 110.6, 33.6, 0.0, 0.4),
        ("边界均匀 东南西0.3", 113.4, 33.6, -0.3, 0.0),
        ("边界均匀 西北南0.3", 110.6, 36.4, 0.0, -0.3),
        ("边界均匀 东北西南0.3", 113.4, 36.4, -0.3, -0.3),
        ("边界均匀 西缘东0.5", 110.5, 35.0, 0.5, 0.0),
        ("边界均匀 南缘北0.5", 112.0, 33.4, 0.0, 0.5),
        ("边界均匀 东缘西0.6", 113.5, 35.0, -0.6, 0.0),
    ]:
        rain, lon, lat, f = make_blob(lon0, lat0)
        uu, vv = uv_uniform(f.shape, ud, vd)
        cases.append((title, rain, lon, lat, f, uu, vv))

    # —— 域内 · 切变 ——
    for title, maker, a, b in [
        ("域内切变 lat弱", uv_shear_lat, 0.2, 0.05),
        ("域内切变 lat强", uv_shear_lat, 0.5, 0.15),
        ("域内切变 lon", uv_shear_lon, 0.25, 0.4),
        ("域内切变 both", uv_shear_both, 0.35, 0.35),
    ]:
        rain, lon, lat, f = make_blob(112.0, 35.0)
        uu, vv = maker(lon, lat, a, b)
        cases.append((title, rain, lon, lat, f, uu, vv))

    rain, lon, lat, f = make_blob(112.0, 35.5)
    uu, vv = uv_shear_lat(lon, lat, 0.45, -0.1)
    cases.append(("域内切变 偏北斑", rain, lon, lat, f, uu, vv))

    # —— 边界 · 切变 ——
    for title, lon0, lat0, maker, a, b in [
        ("边界切变 西南lat", 110.6, 33.6, uv_shear_lat, 0.4, 0.1),
        ("边界切变 西南lon", 110.6, 33.6, uv_shear_lon, 0.3, 0.3),
        ("边界切变 西南both", 110.6, 33.6, uv_shear_both, 0.4, 0.25),
        ("边界切变 东南lat", 113.4, 33.6, uv_shear_lat, 0.35, 0.2),
        ("边界切变 西北lat", 110.6, 36.4, uv_shear_lat, 0.3, -0.25),
        ("边界切变 东北both", 113.4, 36.4, uv_shear_both, 0.5, 0.4),
        ("边界切变 西缘lat", 110.5, 35.0, uv_shear_lat, 0.6, 0.0),
    ]:
        rain, lon, lat, f = make_blob(lon0, lat0)
        uu, vv = maker(lon, lat, a, b)
        cases.append((title, rain, lon, lat, f, uu, vv))

    # —— 复合形态 ——
    rain, lon, lat, f = make_two_blob()
    uu, vv = uv_uniform(f.shape, 0.3, 0.1)
    cases.append(("复合 三斑均匀", rain, lon, lat, f, uu, vv))

    rain, lon, lat, f = make_two_blob()
    uu, vv = uv_shear_lat(lon, lat, 0.4, 0.15)
    cases.append(("复合 三斑切变", rain, lon, lat, f, uu, vv))

    rain, lon, lat, f = make_blob(110.6, 33.6, amp=30, sig=0.5)
    uu, vv = uv_shear_both(lon, lat, 0.55, 0.45)
    cases.append(("复合 大斑边界切变", rain, lon, lat, f, uu, vv))

    return cases


def main():
    cases = build_cases()
    print("=" * 76)
    print("扩大测试 → extrapolate_like_lagrangian (= n_iter=0 + P1)")
    print(f"模块: {os.path.join(RAIN_SRC, 'utils', 'cressman_extrap_reprocess.py')}")
    print(f"{'用例':<24} {'meanAbs':>12} {'maxAbs':>12} {'一致':>6}")
    print("-" * 76)

    results = []
    for spec in cases:
        r = run_one(*spec)
        results.append(r)
        print(
            f"{r['name']:<24} {r['meanAbs']:12.2e} {r['maxAbs']:12.2e} "
            f"{'是' if r['ok'] else '否':>6}"
        )

    n_ok = sum(1 for r in results if r["ok"])
    print("-" * 76)
    print(f"完全一致: {n_ok}/{len(results)}")
    if n_ok == len(results):
        print("结论：全部通过 → 方案已抽离，后续用 extrapolate_like_lagrangian。")
    else:
        print("失败用例:")
        for r in results:
            if not r["ok"]:
                print(f"  - {r['name']}: maxAbs={r['maxAbs']}")
    print("=" * 76)

    import matplotlib.pyplot as plt

    pick = [
        "域内均匀 东0.3", "边界均匀 西南东1.0", "域内切变 lat强",
        "边界切变 西南lat", "边界切变 东北both", "复合 三斑切变",
    ]
    by = {r["name"]: r for r in results}
    fig, axes = plt.subplots(6, 4, figsize=(12, 14), constrained_layout=True)
    for row, name in enumerate(pick):
        r = by[name]
        vmax = max(r["rain0"].max(), r["L"].max(), r["A"].max(), 1.0)
        dmax = max(r["maxAbs"], 1e-3)
        for col, (data, sub, cmap, vmin, vmax_) in enumerate([
            (r["rain0"], "输入", "Blues", 0, vmax),
            (r["L"], "Lagrangian", "Blues", 0, vmax),
            (r["A"], "n_iter0+P1模块", "Blues", 0, vmax),
            (r["diff"], f"差 {r['maxAbs']:.0e}", "RdBu_r", -dmax, dmax),
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

    fig.suptitle(f"n_iter=0+P1 扩大测试  {n_ok}/{len(results)}", fontsize=12)
    png = os.path.join(HERE, "demo_advection_niter0_p1.png")
    fig.savefig(png, dpi=120)
    print(f"图: {png}")


if __name__ == "__main__":
    main()
