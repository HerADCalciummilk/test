# -*- coding: utf-8 -*-
"""
同背景 + 同站点，对比三个结果：

  ① 原版 GressMan（本身就是：差值摊开 + 加回背景）
  ② 项目 Cressman 直接插（绝对值盖到背景上）
  ③ 项目：先算「站−背景」差值 → 用项目 Cressman 摊开 → 再加回背景

半径：原版用度；项目用 R_km = R° × 111.2 × cos(lat)（图上最大半径与原版一致）

运行::
    python demo_cressman_innovation_add.py
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
KM_PER_DEG = ER * math.pi / 180.0


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def bg_at_station(bg, lon0, lat0):
    """背景场在站点最近格点的值。"""
    lon, lat = np.asarray(bg.lon), np.asarray(bg.lat)
    i = int(np.argmin(np.abs(lon - lon0)))
    j = int(np.argmin(np.abs(lat - lat0)))
    return float(arr(bg)[j, i]), i, j


def footprint_deg(out, bg, lon0, lat0, eps=1e-3):
    a, b = arr(out), arr(bg)
    mask = np.abs(a - b) > eps
    if not np.any(mask):
        return 0.0, 0
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    d = np.sqrt((lon2d[mask] - lon0) ** 2 + (lat2d[mask] - lat0) ** 2)
    return float(d.max()), int(mask.sum())


def vs_ref(name, out, ref):
    d = arr(out) - arr(ref)
    return (f"{name}: meanAbs={np.mean(np.abs(d)):.4f}  "
            f"maxAbs={np.max(np.abs(d)):.4f}  rmse={np.sqrt(np.mean(d*d)):.4f}")


def main():
    # ===== 同一份输入 =====
    lon0, lat0 = 110.0, 35.0
    sta_val = 20.0
    r_deg = [0.8, 0.6, 0.4, 0.2]
    # 图上最大半径对齐：再乘 cos(lat)
    r_km = [r * KM_PER_DEG * math.cos(math.radians(lat0)) for r in r_deg]

    half, dlon = 1.2, 0.05
    grid = meb.grid([lon0 - half, lon0 + half, dlon],
                    [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    sta = creat_M3_grd([lon0], [lat0], [sta_val], rpt="2024010108", dtime=0)
    gi = meb.basicdata.get_grid_of_data(bg)

    bg_sta, _, _ = bg_at_station(bg, lon0, lat0)
    innov_val = sta_val - bg_sta
    sta_innov = creat_M3_grd([lon0], [lat0], [innov_val], rpt="2024010108", dtime=0)

    # ===== 三个结果 =====
    # ① 原版
    out_原版 = InterpSg(
        method="cressman", r_list=r_deg, reprocess=True, degree_blend=1.0
    ).process(sta, background=bg.copy())

    # ② 项目直接插（绝对值）
    out_项目直接 = InterpSg(
        method="cressman", r_list=r_km, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)

    # ③ 项目：差值场摊开 + 加回背景
    #    背景传 None → 初值 0，摊的是「站−背景」；再与背景相加
    out_差值场 = InterpSg(
        method="cressman", r_list=r_km, reprocess=False, nearNum=8
    ).process(sta_innov, grid=gi, background=None)
    out_项目累加 = bg.copy()
    out_项目累加.data = [[[[arr(bg) + arr(out_差值场)]]]]

    results = [
        ("① 原版", out_原版, f"半径 {r_deg} 度"),
        ("② 项目直接插", out_项目直接, f"半径 {[round(x,1) for x in r_km]} km，盖绝对值"),
        ("③ 项目差值累加", out_项目累加,
         f"先摊 (站−背景)={innov_val:.2f}，再 + 背景"),
    ]

    print("=" * 70)
    print("输入相同：背景 + 单站")
    print(f"  站 ({lon0},{lat0})={sta_val}，背景站处={bg_sta:.3f}，差值={innov_val:.3f}")
    print(f"  项目半径 = R°×{KM_PER_DEG:.2f}×cos({lat0}°) → {[round(x,1) for x in r_km]} km")
    print()
    for title, out, tip in results:
        md, n = footprint_deg(out, bg, lon0, lat0)
        print(f"{title}")
        print(f"  {tip}")
        print(f"  改动格点={n}, 图上最大半径={md:.3f}°")
        print()

    print("相对 ①原版：")
    print(" ", vs_ref("②直接插", out_项目直接, out_原版))
    print(" ", vs_ref("③差值累加", out_项目累加, out_原版))
    print("=" * 70)

    # ===== 图：左=场，右=减背景；第4行单独画差值场 =====
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, axes = plt.subplots(4, 2, figsize=(8, 11), constrained_layout=True)
    lon, lat = np.asarray(bg.lon), np.asarray(bg.lat)
    bg2 = arr(bg)

    panels = results + [
        ("差值场(摊开后)", out_差值场, "尚未加背景，仅创新增量"),
    ]
    for row, (title, out, tip) in enumerate(panels):
        a = arr(out)
        ax0, ax1 = axes[row, 0], axes[row, 1]
        if row < 3:
            im0 = ax0.pcolormesh(lon, lat, a, shading="auto", cmap="Blues")
            im1 = ax1.pcolormesh(lon, lat, a - bg2, shading="auto",
                                 cmap="RdBu_r", vmin=-15, vmax=15)
            ax1.set_title(f"{title} · 减背景", fontsize=9)
        else:
            im0 = ax0.pcolormesh(lon, lat, a, shading="auto", cmap="RdBu_r",
                                 vmin=-15, vmax=15)
            im1 = ax1.pcolormesh(lon, lat, a, shading="auto", cmap="RdBu_r",
                                 vmin=-15, vmax=15)
            ax1.set_title("同左（差值场本身）", fontsize=9)
        ax0.set_title(f"{title}\n{tip}", fontsize=9)
        for ax in (ax0, ax1):
            ax.plot(lon0, lat0, "r*", ms=10)
            ax.add_patch(Circle((lon0, lat0), r_deg[0], fill=False,
                                ec="lime", lw=1.0, ls="--"))
            ax.set_aspect("equal")
        fig.colorbar(im0, ax=ax0, fraction=0.05)
        fig.colorbar(im1, ax=ax1, fraction=0.05)

    fig.suptitle(
        "①原版  ②项目直接插  ③项目差值累加(=差值场+背景)   绿虚线=0.8°",
        fontsize=11,
    )
    png = os.path.join(HERE, "demo_cressman_innovation_add.png")
    fig.savefig(png, dpi=120)
    print(f"图: {png}")
    print("看相对原版误差：③（差值累加）应明显小于 ②（直接插）。")


if __name__ == "__main__":
    main()
