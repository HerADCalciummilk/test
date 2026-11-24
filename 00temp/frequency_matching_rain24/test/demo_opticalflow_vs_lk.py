# -*- coding: utf-8 -*-
"""
同输入两场雨：对比原版 OpticalFlow（度 UV）vs 项目 LK（像素 UV）。

  - 构造 before / next（next = before 整体东移已知位移，便于对照「真值」）
  - A = OpticalFlow → u,v（度/步）
  - B = LK → u,v（像素/步），再换算成度：u_度 = u_像素 × dlon
  - 图：u/v 场 + 换算后 B−A，讨论如何让 LK 的 UV 接近 OpticalFlow

运行::
    python demo_opticalflow_vs_lk.py
"""
from __future__ import annotations

import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
OF_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "optical_flow_nowcast"))

TEMP = os.path.normpath(os.path.join(HERE, "..", ".."))
SHARED_UTILS = os.path.join(TEMP, "utils")

# 1) 原版 OpticalFlow
sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]
from frequency_matching_rain24_plugin import OpticalFlow  # noqa: E402

# 2) 项目 LK（需要共享 utils.base_plugin + db_trans）
for k in list(sys.modules):
    if k == "utils" or k.startswith("utils."):
        del sys.modules[k]
sys.path.insert(0, SHARED_UTILS)
sys.path.insert(0, TEMP)
sys.path.insert(0, OF_ROOT)
# 命名空间 utils：共享 base_plugin
import utils as _utils  # noqa: E402
if hasattr(_utils, "__path__"):
    pass
from src.lk_plugin import LK, forecast as lk_forecast  # noqa: E402

import meteva.base as meb  # noqa: E402


def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def make_pair(dlon=0.1, true_u_deg=0.3, true_v_deg=0.0):
    """before 雨斑；next = 东移 true_u_deg（用滚动近似，便于有解析真值）。"""
    grid = meb.grid([110.0, 114.0, dlon], [33.0, 37.0, dlon])
    before = meb.grid_data(grid)
    lon = np.asarray(before.lon)
    lat = np.asarray(before.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field0 = 25.0 * np.exp(-((lon2d - 111.8) ** 2 + (lat2d - 35.0) ** 2) / (0.35 ** 2))
    # 东移：用插值把场移到 lon - true_u
    from scipy.ndimage import map_coordinates
    # 目标格点来自「西边」：后向取样
    jy, ix = np.meshgrid(np.arange(len(lat)), np.arange(len(lon)), indexing="ij")
    src_x = ix - true_u_deg / dlon
    src_y = jy - true_v_deg / dlon
    field1 = map_coordinates(field0, [src_y, src_x], order=1, mode="nearest")

    before.data = [[[[field0]]]]
    nxt = before.copy()
    nxt.data = [[[[field1]]]]
    return before, nxt, dlon, true_u_deg, true_v_deg, lon, lat


def run_opticalflow(before, nxt, min_window=(5.0, 5.0)):
    u0 = before.copy()
    v0 = before.copy()
    u0.data = [[[[np.zeros_like(arr(before))]]]]
    v0.data = [[[[np.zeros_like(arr(before))]]]]
    gd_output = [u0, v0]
    # 阈值放宽，保证合成场能进窗方程
    OpticalFlow.get_optical_flow(
        before, nxt, [list(min_window)], gd_output,
        rain_limit=1.0, delta_rain_limit=0.1, num_limit=30,
    )
    return arr(gd_output[0]), arr(gd_output[1])


def run_lk(before, nxt):
    """直接调 lk_plugin.forecast，避开 meb 时间轴检查。"""
    stack = np.stack([arr(before), arr(nxt)], axis=0)
    # 降噪/疏化关掉，少干扰合成场
    uv = lk_forecast(
        stack,
        dense=True,
        size_opening=0,
        decl_scale=0,
        nr_std_outlier=5,
        verbose=False,
    )
    uv = np.asarray(uv, dtype=float)
    if uv.shape[0] != 2:
        raise RuntimeError(f"LK 返回形状异常: {uv.shape}")
    return uv[0], uv[1]


def score(tag, pred, ref):
    d = pred - ref
    return (f"{tag}: meanAbs={np.mean(np.abs(d)):.4f}  "
            f"rmse={np.sqrt(np.mean(d*d)):.4f}  "
            f"mean(pred)={np.mean(pred):.4f}  mean(ref)={np.mean(ref):.4f}")


def main():
    before, nxt, dlon, true_u, true_v, lon, lat = make_pair()
    print("=" * 64)
    print("OpticalFlow vs LK（同 before/next）")
    print(f"  合成真值位移: u={true_u}°/步, v={true_v}°/步  (dlon={dlon})")
    print()

    u_of, v_of = run_opticalflow(before, nxt)
    print(f"A OpticalFlow:  mean u={np.mean(u_of):.4f}°  mean v={np.mean(v_of):.4f}°")

    try:
        u_px, v_px = run_lk(before, nxt)
    except Exception as e:
        print(f"LK 运行失败: {e}")
        print("请检查 cv2/skimage 等依赖；本脚本其余部分已给出 OpticalFlow 侧。")
        return

    u_lk_deg = u_px * dlon
    v_lk_deg = v_px * dlon
    print(f"B LK(像素):     mean u={np.mean(u_px):.4f}px  mean v={np.mean(v_px):.4f}px")
    print(f"B LK→度:        mean u={np.mean(u_lk_deg):.4f}°  mean v={np.mean(v_lk_deg):.4f}°")
    print()
    print("换算后相对 OpticalFlow：")
    print(" ", score("u", u_lk_deg, u_of))
    print(" ", score("v", v_lk_deg, v_of))
    print("=" * 64)

    import matplotlib.pyplot as plt

    umax = max(np.max(np.abs(u_of)), np.max(np.abs(u_lk_deg)), 1e-3)
    fig, axes = plt.subplots(2, 3, figsize=(11, 7), constrained_layout=True)

    im = axes[0, 0].pcolormesh(lon, lat, u_of, shading="auto", cmap="RdBu_r",
                               vmin=-umax, vmax=umax)
    axes[0, 0].set_title("A OpticalFlow u（度）", fontsize=11)
    fig.colorbar(im, ax=axes[0, 0], fraction=0.046)

    im = axes[0, 1].pcolormesh(lon, lat, u_lk_deg, shading="auto", cmap="RdBu_r",
                               vmin=-umax, vmax=umax)
    axes[0, 1].set_title("B LK→度 u", fontsize=11)
    fig.colorbar(im, ax=axes[0, 1], fraction=0.046)

    d = u_lk_deg - u_of
    dmax = max(np.max(np.abs(d)), 1e-3)
    im = axes[0, 2].pcolormesh(lon, lat, d, shading="auto", cmap="RdBu_r",
                               vmin=-dmax, vmax=dmax)
    axes[0, 2].set_title("B−A  (u 差)", fontsize=11)
    fig.colorbar(im, ax=axes[0, 2], fraction=0.046)

    axes[1, 0].pcolormesh(lon, lat, arr(before), shading="auto", cmap="Blues")
    axes[1, 0].set_title("输入 before", fontsize=11)
    axes[1, 1].pcolormesh(lon, lat, arr(nxt), shading="auto", cmap="Blues")
    axes[1, 1].set_title("输入 next（已知东移）", fontsize=11)
    axes[1, 2].axis("off")
    axes[1, 2].text(
        0.05, 0.55,
        f"真值 u={true_u}°\n"
        f"OF mean u={np.mean(u_of):.3f}°\n"
        f"LK mean u={np.mean(u_lk_deg):.3f}°\n\n"
        "下一步讨论：如何让 LK 的 UV\n"
        "在换算后更接近 OpticalFlow\n"
        "（窗聚合 / 多样本 / 阈值等）",
        fontsize=11, transform=axes[1, 2].transAxes,
    )
    for ax in axes[0]:
        ax.set_aspect("equal")
    for ax in axes[1, :2]:
        ax.set_aspect("equal")

    fig.suptitle("算 UV：OpticalFlow(度) vs LK(像素→度)", fontsize=13)
    png = os.path.join(HERE, "demo_opticalflow_vs_lk.png")
    fig.savefig(png, dpi=130)
    print(f"图: {png}")


if __name__ == "__main__":
    main()
