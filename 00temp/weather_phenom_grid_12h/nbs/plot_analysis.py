# -*- coding: utf-8 -*-
"""
真实数据结果合理性分析绘图脚本
================================
数据来源：PHENOM/2026030100/ 下 3 个真实输出电码NC文件（012h/024h/036h，1201×1401全国网格）
目的：通过可视化手段直观检验判识结果在空间分布、时效演变、逻辑关系占比等维度上是否合理

运行方式（需 met 虚拟环境，含 xarray/matplotlib）：
    C:\\Users\\Administrator\\miniconda3\\envs\\met\\python.exe nbs/plot_analysis.py

输出：docs/figures/ 下生成 4 张 PNG 图
    fig1_spatial_categories.png  三时效天气大类空间分布对比图
    fig2_category_bar.png        三时效天气大类占比柱状图
    fig3_logic_relation_bar.png  三时效逻辑关系(单一/转/间/伴有)占比柱状图
    fig4_spatial_logic_036.png   036h 逻辑关系空间分布图
"""
import os
import sys

import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ── 路径配置 ──────────────────────────────────────────────
INIT_TIME = "2026030100"
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "PHENOM", INIT_TIME)
FIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "docs", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

SEGMENTS = [("012", "012h（第1时段）"), ("024", "024h（第2时段）"), ("036", "036h（第3时段）")]

# ── 天气现象大类归并（用于着色/统计，key为AA电码）──────────
CATEGORY_MAP = {
    "00": "晴", "01": "多云", "02": "阴",
    "04": "雨类", "05": "雨类", "06": "雨类", "07": "雨类", "08": "雨类", "09": "雨类",
    "10": "雨类", "11": "雨类", "12": "雨类", "19": "雨类",
    "14": "雪类", "15": "雪类", "16": "雪类", "17": "雪类", "36": "雪类", "37": "雪类",
    "20": "沙尘", "30": "沙尘", "31": "沙尘",
    "61": "雾", "62": "雾", "63": "雾", "64": "雾", "65": "雾",
    "55": "霾", "56": "霾", "57": "霾", "58": "霾",
}
CATEGORIES = ["晴", "多云", "阴", "雨类", "雪类", "雾", "霾", "沙尘", "其他"]
CAT_COLORS = ["#87CEEB", "#C0C0C0", "#708090", "#1E90FF",
              "#E0FFFF", "#A9A9A9", "#8B7355", "#DEB887", "#000000"]
CAT_TO_IDX = {c: i for i, c in enumerate(CATEGORIES)}

# AA(0~99) -> 大类索引 的快速查表
_CAT_LOOKUP = np.full(100, len(CATEGORIES) - 1, dtype=np.int8)  # 默认"其他"
for _code, _cat in CATEGORY_MAP.items():
    _CAT_LOOKUP[int(_code)] = CAT_TO_IDX[_cat]

LOGIC_NAMES = ["单一", "转", "间", "伴有"]
LOGIC_COLORS = ["#4CAF50", "#FF9800", "#2196F3", "#9C27B0"]


def load_phenom(fh: str):
    """读取一个时效的真实输出NC，返回 (综合电码网格int64, lat, lon)"""
    path = os.path.join(DATA_DIR, f"{INIT_TIME}.{fh}.nc")
    ds = xr.open_dataset(path)
    arr = ds["phenom_code"].values.squeeze().astype(np.int64)
    lat = ds["lat"].values
    lon = ds["lon"].values
    ds.close()
    return arr, lat, lon


def decode_grid(code_grid: np.ndarray):
    """矢量化解析5位综合电码：K + AA + BB -> (k, aa, bb) 三个网格"""
    k = code_grid // 10000
    aa = (code_grid // 100) % 100
    bb = code_grid % 100
    return k, aa, bb


def category_grid(aa_grid: np.ndarray) -> np.ndarray:
    """AA电码网格 -> 天气大类索引网格"""
    return _CAT_LOOKUP[aa_grid.astype(np.int64)]


def main():
    print("=== 加载真实输出数据 ===")
    data = {}
    for fh, label in SEGMENTS:
        code_grid, lat, lon = load_phenom(fh)
        k, aa, bb = decode_grid(code_grid)
        cat = category_grid(aa)
        data[fh] = dict(code=code_grid, lat=lat, lon=lon, k=k, aa=aa, bb=bb, cat=cat, label=label)
        print(f"  {fh}: 网格 {code_grid.shape}，复合现象(K!=0)占比 "
              f"{(k != 0).mean() * 100:.2f}%")

    cmap = ListedColormap(CAT_COLORS)
    norm = BoundaryNorm(np.arange(len(CATEGORIES) + 1) - 0.5, cmap.N)
    legend_handles = [Patch(facecolor=CAT_COLORS[i], edgecolor="gray", label=CATEGORIES[i])
                       for i in range(len(CATEGORIES))]

    # ── 图1：三时效天气大类空间分布对比 ──────────────────
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), constrained_layout=True)
    for ax, (fh, _) in zip(axes, SEGMENTS):
        d = data[fh]
        extent = [d["lon"].min(), d["lon"].max(), d["lat"].min(), d["lat"].max()]
        ax.imshow(d["cat"], origin="lower", extent=extent, cmap=cmap, norm=norm,
                  interpolation="nearest", aspect="auto")
        ax.set_title(f"{d['label']} 天气大类空间分布")
        ax.set_xlabel("经度")
        ax.set_ylabel("纬度")
    fig.legend(handles=legend_handles, loc="lower center", ncol=len(CATEGORIES),
               bbox_to_anchor=(0.5, -0.05))
    fig.suptitle(f"起报时次 {INIT_TIME}  天气现象大类空间分布（三时效对比）", fontsize=14)
    out1 = os.path.join(FIG_DIR, "fig1_spatial_categories.png")
    fig.savefig(out1, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[图1] 已保存 → {out1}")

    # ── 图2：三时效天气大类占比柱状图 ────────────────────
    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(CATEGORIES))
    width = 0.25
    for i, (fh, _) in enumerate(SEGMENTS):
        cat = data[fh]["cat"]
        total = cat.size
        pct = [np.sum(cat == j) / total * 100 for j in range(len(CATEGORIES))]
        ax.bar(x + (i - 1) * width, pct, width, label=data[fh]["label"],
               color=CAT_COLORS[i % len(CAT_COLORS)] if False else None)
    ax.set_xticks(x)
    ax.set_xticklabels(CATEGORIES)
    ax.set_ylabel("格点占比 (%)")
    ax.set_title(f"起报时次 {INIT_TIME}  天气大类占比对比（三时效）")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    out2 = os.path.join(FIG_DIR, "fig2_category_bar.png")
    fig.savefig(out2, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[图2] 已保存 → {out2}")

    # ── 图3：三时效逻辑关系占比柱状图 ────────────────────
    fig, ax = plt.subplots(figsize=(8, 6))
    x = np.arange(len(LOGIC_NAMES))
    width = 0.25
    for i, (fh, _) in enumerate(SEGMENTS):
        k = data[fh]["k"]
        total = k.size
        pct = [np.sum(k == j) / total * 100 for j in range(len(LOGIC_NAMES))]
        ax.bar(x + (i - 1) * width, pct, width, label=data[fh]["label"])
    ax.set_xticks(x)
    ax.set_xticklabels(LOGIC_NAMES)
    ax.set_ylabel("格点占比 (%)")
    ax.set_yscale("symlog")
    ax.set_title(f"起报时次 {INIT_TIME}  逻辑关系(单一/转/间/伴有)占比对比\n"
                 f"（合理性预期：单一 应占绝大多数，转/间/伴有 应为少数过渡区域）")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    out3 = os.path.join(FIG_DIR, "fig3_logic_relation_bar.png")
    fig.savefig(out3, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[图3] 已保存 → {out3}")

    # ── 图4：036h 逻辑关系空间分布图（检验复合现象是否分布在过渡区域）
    fh_last = SEGMENTS[-1][0]
    d = data[fh_last]
    logic_cmap = ListedColormap(LOGIC_COLORS)
    logic_norm = BoundaryNorm(np.arange(len(LOGIC_NAMES) + 1) - 0.5, logic_cmap.N)
    fig, ax = plt.subplots(figsize=(9, 7))
    extent = [d["lon"].min(), d["lon"].max(), d["lat"].min(), d["lat"].max()]
    im = ax.imshow(d["k"], origin="lower", extent=extent, cmap=logic_cmap, norm=logic_norm,
                   interpolation="nearest", aspect="auto")
    ax.set_title(f"{d['label']} 逻辑关系空间分布（{INIT_TIME}）")
    ax.set_xlabel("经度")
    ax.set_ylabel("纬度")
    handles = [Patch(facecolor=LOGIC_COLORS[i], edgecolor="gray", label=LOGIC_NAMES[i])
               for i in range(len(LOGIC_NAMES))]
    ax.legend(handles=handles, loc="upper right")
    out4 = os.path.join(FIG_DIR, "fig4_spatial_logic_036.png")
    fig.savefig(out4, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[图4] 已保存 → {out4}")

    print("\n全部图片已生成至:", FIG_DIR)


if __name__ == "__main__":
    main()
