# -*- coding: utf-8 -*-
"""
同背景+同站点，三结果对比影响范围。

  ① 原版（半径单位：度，圆是「经纬度平面圆」）
  ② 项目默认半径（未对齐）
  ③ 项目半径对齐（公里→再乘 cos(lat)，让图上看起来接近原版）

说明：原版截断是 sqrt(Δlon²+Δlat²)≤R°；项目是球面公里圆。
只乘 111km/° 时，中纬度上公里圆在图上会显得更「胖」（你看到的偏大）。
再乘 cos(lat) 后，东西向宽度才和原版的度制圆接近。

运行: python demo_cressman_radius_align.py
"""
from __future__ import annotations

import math
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
TEMP = os.path.normpath(os.path.join(HERE, "..", ".."))
PROJ_ROOT = os.path.join(TEMP, "interpolation_station_grid")
PROJ_SRC = os.path.join(PROJ_ROOT, "src")

sys.path[:0] = [PROJ_ROOT, PROJ_SRC]
from interp_sg_plugin import InterpSg

for k in list(sys.modules):
    if k == "utils" or k.startswith("utils."):
        del sys.modules[k]
for p in (PROJ_ROOT, PROJ_SRC,
          os.path.join(TEMP, "interp_gg_linear"),
          os.path.join(TEMP, "interp_gg_linear", "src")):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils"), os.path.join(TEMP, "utils")]
from utils.data_proc import creat_M3_grd

import meteva.base as meb
import meteva_base

ER = float(meteva_base.basicdata.const.ER)
KM_PER_DEG = ER * math.pi / 180.0  # ≈111.2


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data).squeeze()


def footprint_deg(out, bg, lon0, lat0, eps=1e-3):
    """相对背景有改动处，平面经纬度距离的最大半径（度）。"""
    a, b = arr(out), arr(bg)
    mask = np.abs(a - b) > eps
    if not np.any(mask):
        return 0.0, 0
    lon, lat = np.asarray(bg.lon), np.asarray(bg.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    d = np.sqrt((lon2d[mask] - lon0) ** 2 + (lat2d[mask] - lat0) ** 2)
    return float(d.max()), int(mask.sum())


def main():
    lon0, lat0 = 110.0, 35.0
    sta_val = 20.0
    r_deg = [0.8, 0.6, 0.4, 0.2]
    # 只乘 111：中纬度图上会偏大（旧对齐）
    r_km_raw = [r * KM_PER_DEG for r in r_deg]
    # 再乘 cos(lat)：东西向宽度贴近原版度制圆（目视对齐）
    r_km = [r * KM_PER_DEG * math.cos(math.radians(lat0)) for r in r_deg]
    r_default = [60, 40, 20]  # 千米（统一包 reprocess=False 默认）

    half, dlon = 1.2, 0.05
    grid = meb.grid([lon0 - half, lon0 + half, dlon],
                    [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    sta = creat_M3_grd([lon0], [lat0], [sta_val], rpt="2024010108", dtime=0)
    gi = meb.basicdata.get_grid_of_data(bg)

    out1 = InterpSg(
        method="cressman", r_list=r_deg, reprocess=True, degree_blend=1.0
    ).process(sta, background=bg.copy())
    out2 = InterpSg(
        method="cressman", r_list=r_default, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)
    out3 = InterpSg(
        method="cressman", r_list=r_km, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)
    # 对照：旧对齐（不乘 cos）——只打印足迹，不占主图
    out3_old = InterpSg(
        method="cressman", r_list=r_km_raw, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)

    results = [
        ("① 原版", out1, f"R={r_deg} 度"),
        ("② 项目默认", out2, f"R={r_default}"),
        ("③ 项目对齐", out3,
         f"R={[round(x,1) for x in r_km]} km  (=R°×111×cos({lat0}°))"),
    ]

    print("为何「只×111」会目测偏大：")
    print(f"  原版圆：经纬度平面  √(Δlon²+Δlat²) ≤ {r_deg[0]}°")
    print(f"  项目圆：球面公里距 ≤ R_km")
    print(f"  lat={lat0}° 时，{r_deg[0]}°经度 ≈ {r_deg[0]*KM_PER_DEG*math.cos(math.radians(lat0)):.1f} km，")
    print(f"  若 R_km={r_deg[0]*KM_PER_DEG:.1f}（只×111），东西向可伸到 "
          f"{r_deg[0]/math.cos(math.radians(lat0)):.2f}° > {r_deg[0]}° → 图上看更大。")
    print()
    for title, out, tip in results:
        md, n = footprint_deg(out, bg, lon0, lat0)
        print(f"{title}:  {tip}")
        print(f"         改动格点={n},  图上最大半径={md:.3f}°")
    md_old, _ = footprint_deg(out3_old, bg, lon0, lat0)
    print(f"（对照）只×111、不乘cos: 图上最大半径={md_old:.3f}°  ← 就是你刚才看到偏大的那种")
    print()

    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, axes = plt.subplots(3, 2, figsize=(8, 9), constrained_layout=True)
    lon, lat = np.asarray(bg.lon), np.asarray(bg.lat)
    bg2 = arr(bg)
    for row, (title, out, tip) in enumerate(results):
        a = arr(out)
        ax0, ax1 = axes[row, 0], axes[row, 1]
        im0 = ax0.pcolormesh(lon, lat, a, shading="auto", cmap="Blues")
        im1 = ax1.pcolormesh(lon, lat, a - bg2, shading="auto", cmap="RdBu_r",
                             vmin=-15, vmax=15)
        ax0.set_title(f"{title}\n{tip}", fontsize=9)
        ax1.set_title(f"{title} · 减背景", fontsize=9)
        for ax in (ax0, ax1):
            ax.plot(lon0, lat0, "r*", ms=10)
            # 原版理论圆（度制），方便和色斑比大小
            ax.add_patch(Circle((lon0, lat0), r_deg[0], fill=False,
                                ec="lime", lw=1.2, ls="--",
                                label="原版0.8°圆"))
            ax.set_aspect("equal")
        fig.colorbar(im0, ax=ax0, fraction=0.05)
        fig.colorbar(im1, ax=ax1, fraction=0.05)

    axes[0, 1].legend(loc="upper right", fontsize=8)
    fig.suptitle("①原版  ②项目默认  ③项目对齐(×111×cos lat)   绿虚线=原版0.8°圆", fontsize=11)
    png = os.path.join(HERE, "demo_cressman_three_results.png")
    fig.savefig(png, dpi=120)
    print(f"图: {png}")
    print("看右列+绿圈：③应贴绿圈；②仍铺满。")


if __name__ == "__main__":
    main()
