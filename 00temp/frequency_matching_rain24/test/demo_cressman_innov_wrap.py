# -*- coding: utf-8 -*-
"""
方案测试：创新包装 + postprocess 同款「度制圆裁增量」半径方法。

  A = 原版
  B = 项目直接插（默认 r_list）
  C = 创新包装：
        逐半径：差额=站−背景 → 项目摊差额 →
        增量只保留 √(Δlon²+Δlat²)≤R° 内（与 postprocess_align 相同）→ 加回背景
        项目 r_list 用足够大的公里半径盖住该度制圆即可，范围由裁剪决定，不靠 cos(lat)

图：上行三结果；下行 B−A、C−A、剖面。

运行::
    python demo_cressman_innov_wrap.py
"""
from __future__ import annotations

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

R_DEFAULT = [60.0, 40.0, 20.0]  # 千米


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def score(tag, pred, ref):
    d = pred - ref
    p, r = pred.ravel(), ref.ravel()
    if np.std(p) < 1e-12 or np.std(r) < 1e-12:
        corr = float("nan")
    else:
        corr = float(np.corrcoef(p, r)[0, 1])
    return {
        "tag": tag,
        "meanAbs": float(np.mean(np.abs(d))),
        "rmse": float(np.sqrt(np.mean(d * d))),
        "maxAbs": float(np.max(np.abs(d))),
        "corr": corr,
    }


def main():
    lon0, lat0 = 110.0, 35.0
    sta_val = 20.0
    r_degs = [0.8, 0.6, 0.4, 0.2]

    half, dlon = 1.2, 0.05
    grid = meb.grid([lon0 - half, lon0 + half, dlon],
                    [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon2d, lat2d = np.meshgrid(np.asarray(bg.lon), np.asarray(bg.lat))
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    sta = creat_M3_grd([lon0], [lat0], [sta_val], rpt="2024010108", dtime=0)
    gi = meb.basicdata.get_grid_of_data(bg)
    lon, lat = np.asarray(bg.lon), np.asarray(bg.lat)
    bg2 = arr(bg)

    out_a = InterpSg(
        method="cressman", r_list=r_degs, reprocess=True, degree_blend=1.0
    ).process(sta, background=bg.copy())
    out_b = InterpSg(
        method="cressman", r_list=R_DEFAULT, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)
    out_c = InterpSg(
        method="cressman", r_list=r_degs, reprocess=True, nearNum=8
    ).process(sta, background=bg.copy())
    a, b, c = arr(out_a), arr(out_b), arr(out_c)

    print(a)
    print("=--------------------------------------------------------------------------------------------------------->")
    print(b)
    print("=--------------------------------------------------------------------------------------------------------->")
    print(c)
    print("=--------------------------------------------------------------------------------------------------------->")
    print(a-c)

    # # 改动格点数（应 A≈C，因同用度制圆）
    # def n_touch(x):
    #     return int(np.sum(np.abs(x - bg2) > 1e-3))
    #
    # sb, sc = score("B直接插", b, a), score("C创新+度制圆裁", c, a)
    # print("=" * 60)
    # print("C 半径方法 = postprocess_align 同款：增量保留在 √(Δlon²+Δlat²)≤R°")
    # print(f"改动格点: A={n_touch(a)}  B={n_touch(b)}  C={n_touch(c)}")
    # print("相对原版 A（越小越接近）")
    # print(f"{'方案':<16} {'meanAbs':>10} {'rmse':>10} {'maxAbs':>10} {'相关':>8}")
    # for s in (sb, sc):
    #     print(f"{s['tag']:<16} {s['meanAbs']:10.4f} {s['rmse']:10.4f} "
    #           f"{s['maxAbs']:10.4f} {s['corr']:8.4f}")
    # print("=" * 60)
    #
    # import matplotlib.pyplot as plt
    #
    # vmin = min(a.min(), b.min(), c.min())
    # vmax = max(a.max(), b.max(), c.max())
    # dmax = max(np.abs(b - a).max(), np.abs(c - a).max())
    #
    # fig, axes = plt.subplots(2, 3, figsize=(11, 7), constrained_layout=True)
    # for ax, field, title in zip(
    #     axes[0], (a, b, c),
    #     ("A 原版", "B 项目直接插", "C 创新包装+度制圆裁"),
    # ):
    #     im = ax.pcolormesh(lon, lat, field, shading="auto",
    #                        cmap="Blues", vmin=vmin, vmax=vmax)
    #     ax.plot(lon0, lat0, "r*", ms=8)
    #     ax.set_title(title, fontsize=11)
    #     ax.set_aspect("equal")
    #     fig.colorbar(im, ax=ax, fraction=0.046)
    #
    # im = axes[1, 0].pcolormesh(lon, lat, b - a, shading="auto",
    #                            cmap="RdBu_r", vmin=-dmax, vmax=dmax)
    # axes[1, 0].set_title(f"B−A  meanAbs={sb['meanAbs']:.3f}", fontsize=11)
    # fig.colorbar(im, ax=axes[1, 0], fraction=0.046)
    #
    # im = axes[1, 1].pcolormesh(lon, lat, c - a, shading="auto",
    #                            cmap="RdBu_r", vmin=-dmax, vmax=dmax)
    # axes[1, 1].set_title(f"C−A  meanAbs={sc['meanAbs']:.3f}", fontsize=11)
    # fig.colorbar(im, ax=axes[1, 1], fraction=0.046)
    #
    # j = int(np.argmin(np.abs(lat - lat0)))
    # axes[1, 2].plot(lon, a[j], "k-", lw=2, label="A原版")
    # axes[1, 2].plot(lon, b[j], "C1--", lw=1.5, label="B直接插")
    # axes[1, 2].plot(lon, c[j], "C2-", lw=1.5, label="C创新+裁圆")
    # axes[1, 2].axvline(lon0, color="r", ls=":", lw=1)
    # axes[1, 2].set_title(f"过站剖面 lat={lat[j]:.2f}", fontsize=11)
    # axes[1, 2].legend(fontsize=8)
    # axes[1, 2].grid(True, alpha=0.3)
    #
    # for ax in axes[1, :2]:
    #     ax.plot(lon0, lat0, "r*", ms=8)
    #     ax.set_aspect("equal")
    #
    # fig.suptitle("结果对比：下行差场看谁更接近原版", fontsize=13)
    # png = os.path.join(HERE, "demo_cressman_innov_wrap.png")
    # fig.savefig(png, dpi=130)
    # print(f"图: {png}")


if __name__ == "__main__":
    main()
