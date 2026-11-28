# -*- coding: utf-8 -*-
"""
对齐思路：不改项目影响半径参数，只对「项目结果」再加工。

同背景 + 同站点：

  ① 原版 GressMan
  ② 项目直接插（conf 默认 r_list，参数不动）
  ③ 再加工对齐：
       增量 = 项目结果 − 背景
       只保留落在「原版度制影响圆」内的增量（按最大档 R° 裁剪）
       再在站点处把增量定标成 (站 − 背景)，其余按同一比例缩放
       结果 = 背景 + 定标后的增量

运行::
    python demo_cressman_postprocess_align.py
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

# 项目默认半径 —— 本脚本故意不改它
R_DEFAULT = [60.0, 40.0, 20.0]  # 千米


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def nearest_val(field2d, lon, lat, lon0, lat0):
    i = int(np.argmin(np.abs(lon - lon0)))
    j = int(np.argmin(np.abs(lat - lat0)))
    return float(field2d[j, i]), i, j


def degree_disk_mask(lon, lat, lon0, lat0, r_deg):
    lon2d, lat2d = np.meshgrid(lon, lat)
    return (lon2d - lon0) ** 2 + (lat2d - lat0) ** 2 <= r_deg ** 2


def footprint_deg(out2d, bg2d, lon, lat, lon0, lat0, eps=1e-3):
    mask = np.abs(out2d - bg2d) > eps
    if not np.any(mask):
        return 0.0, 0
    lon2d, lat2d = np.meshgrid(lon, lat)
    d = np.sqrt((lon2d[mask] - lon0) ** 2 + (lat2d[mask] - lat0) ** 2)
    return float(d.max()), int(mask.sum())


def vs_ref(tag, a, ref):
    d = a - ref
    return (f"{tag}: meanAbs={np.mean(np.abs(d)):.4f}  "
            f"maxAbs={np.max(np.abs(d)):.4f}  rmse={np.sqrt(np.mean(d*d)):.4f}")


def postprocess_align(proj2d, bg2d, lon, lat, lon0, lat0, sta_val, r_deg_max):
    """对项目结果再加工：裁剪到原版度制圆 + 站点增量定标。"""
    inc = proj2d - bg2d
    mask = degree_disk_mask(lon, lat, lon0, lat0, r_deg_max)
    inc_cut = np.where(mask, inc, 0.0)

    # 站点处希望最终 = sta_val → 增量目标 = sta_val - bg
    bg_sta, i, j = nearest_val(bg2d, lon, lat, lon0, lat0)
    target_inc = sta_val - bg_sta
    inc_sta = float(inc_cut[j, i])
    if abs(inc_sta) > 1e-6:
        scale = target_inc / inc_sta
    else:
        scale = 1.0
    inc_aligned = inc_cut * scale
    return bg2d + inc_aligned, inc, inc_cut, scale, bg_sta, target_inc


def main():
    lon0, lat0 = 110.0, 35.0
    sta_val = 20.0
    r_deg = [0.8, 0.6, 0.4, 0.2]  # 只用于①原版，以及③裁剪用最大档
    r_cut = max(r_deg)

    half, dlon = 1.2, 0.05
    grid = meb.grid([lon0 - half, lon0 + half, dlon],
                    [lat0 - half, lat0 + half, dlon])
    bg = meb.grid_data(grid)
    lon = np.asarray(bg.lon)
    lat = np.asarray(bg.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    bg.data = [[[[(5 + 3 * np.cos((lon2d - lon0) / half * np.pi)
                   * np.cos((lat2d - lat0) / half * np.pi))]]]]
    bg2 = arr(bg)
    sta = creat_M3_grd([lon0], [lat0], [sta_val], rpt="2024010108", dtime=0)
    gi = meb.basicdata.get_grid_of_data(bg)

    # ① 原版
    out1 = InterpSg(
        method="cressman", r_list=r_deg, reprocess=True, degree_blend=1.0
    ).process(sta, background=bg.copy())
    a1 = arr(out1)

    # ② 项目：默认参数，不调 r_list
    out2 = InterpSg(
        method="cressman", r_list=R_DEFAULT, reprocess=False, nearNum=8
    ).process(sta, grid=gi, background=bg)
    a2 = arr(out2)

    # ③ 对②再加工
    a3, inc_raw, inc_cut, scale, bg_sta, target_inc = postprocess_align(
        a2, bg2, lon, lat, lon0, lat0, sta_val, r_cut)

    print("=" * 70)
    print("不调项目 r_list，只对项目结果再加工")
    print(f"  站 ({lon0},{lat0})={sta_val}，背景站处={bg_sta:.3f}，目标增量={target_inc:.3f}")
    print(f"  项目 r_list 保持默认 {R_DEFAULT}")
    print(f"  再加工：增量裁到原版圆 R≤{r_cut}°，再×定标 scale={scale:.4f}")
    print()

    for tag, a in (("① 原版", a1), ("② 项目原样", a2), ("③ 项目再加工", a3)):
        md, n = footprint_deg(a, bg2, lon, lat, lon0, lat0)
        print(f"{tag}: 改动格点={n}, 图上最大半径={md:.3f}°")
    print()
    print("相对 ①原版：")
    print(" ", vs_ref("②项目原样", a2, a1))
    print(" ", vs_ref("③再加工后", a3, a1))
    print("=" * 70)

    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    fig, axes = plt.subplots(3, 2, figsize=(8, 9), constrained_layout=True)
    panels = [
        ("① 原版", a1, f"GressMan R={r_deg}°"),
        ("② 项目原样", a2, f"默认 r_list={R_DEFAULT}"),
        ("③ 项目再加工", a3, f"裁剪到{r_cut}°圆 + 站点定标×{scale:.2f}"),
    ]
    for row, (title, a, tip) in enumerate(panels):
        ax0, ax1 = axes[row]
        im0 = ax0.pcolormesh(lon, lat, a, shading="auto", cmap="Blues")
        im1 = ax1.pcolormesh(lon, lat, a - bg2, shading="auto",
                             cmap="RdBu_r", vmin=-15, vmax=15)
        ax0.set_title(f"{title}\n{tip}", fontsize=9)
        ax1.set_title(f"{title} · 减背景", fontsize=9)
        for ax in (ax0, ax1):
            ax.plot(lon0, lat0, "r*", ms=10)
            ax.add_patch(Circle((lon0, lat0), r_cut, fill=False,
                                ec="lime", lw=1.2, ls="--"))
            ax.set_aspect("equal")
        fig.colorbar(im0, ax=ax0, fraction=0.05)
        fig.colorbar(im1, ax=ax1, fraction=0.05)

    fig.suptitle("对齐靠「再加工项目结果」，不改项目影响参数", fontsize=12)
    png = os.path.join(HERE, "demo_cressman_postprocess_align.png")
    fig.savefig(png, dpi=120)
    print(f"图: {png}")
    print("右列：②铺满；③被绿圈裁住，范围与①一致（圈内形态仍可因权重不同而不等）。")


if __name__ == "__main__":
    main()
