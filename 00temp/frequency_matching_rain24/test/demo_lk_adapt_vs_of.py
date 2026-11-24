# -*- coding: utf-8 -*-
"""
试 LK 适配链：像素 → 度 → 5° 窗聚合 →（可选）相对 OF 的 gain。

多组合成位移下同时报：
  - 相对 OpticalFlow 的差（产品对齐）
  - 相对真值的差（物理是否变差）

链：
  B0  LK→度（仅换算）
  B1  B0 + 5° 窗聚合（同 OF 半窗步长铺窗，重叠区平均）
  B2  B1 × gain，gain = mean(OF)/mean(B1)（逐案；另报跨案全局 gain）

运行::
    python demo_lk_adapt_vs_of.py
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

sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]
from frequency_matching_rain24_plugin import OpticalFlow  # noqa: E402

for k in list(sys.modules):
    if k == "utils" or k.startswith("utils."):
        del sys.modules[k]
sys.path.insert(0, SHARED_UTILS)
sys.path.insert(0, TEMP)
sys.path.insert(0, OF_ROOT)
import utils as _utils  # noqa: E402, F401
from src.lk_plugin import forecast as lk_forecast  # noqa: E402

import meteva.base as meb  # noqa: E402


# ---------- 合成场 / 估速（与 demo_opticalflow_vs_lk 同风格） ----------

def arr(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def make_pair(dlon=0.1, true_u_deg=0.3, true_v_deg=0.0):
    from scipy.ndimage import map_coordinates

    grid = meb.grid([110.0, 114.0, dlon], [33.0, 37.0, dlon])
    before = meb.grid_data(grid)
    lon = np.asarray(before.lon)
    lat = np.asarray(before.lat)
    lon2d, lat2d = np.meshgrid(lon, lat)
    field0 = 25.0 * np.exp(-((lon2d - 111.8) ** 2 + (lat2d - 35.0) ** 2) / (0.35 ** 2))
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
    OpticalFlow.get_optical_flow(
        before, nxt, [list(min_window)], gd_output,
        rain_limit=1.0, delta_rain_limit=0.1, num_limit=30,
    )
    return arr(gd_output[0]), arr(gd_output[1])


def run_lk(before, nxt):
    stack = np.stack([arr(before), arr(nxt)], axis=0)
    uv = np.asarray(
        lk_forecast(
            stack,
            dense=True,
            size_opening=0,
            decl_scale=0,
            nr_std_outlier=5,
            verbose=False,
        ),
        dtype=float,
    )
    if uv.shape[0] != 2:
        raise RuntimeError(f"LK 返回形状异常: {uv.shape}")
    return uv[0], uv[1]


# ---------- 适配：窗聚合 + gain ----------

def window_aggregate(u, v, dlon, dlat, win_deg=5.0, rain=None, rain_limit=1.0):
    """
    按 OpticalFlow 同款窗心/半窗步长铺窗，窗内均值写回，重叠区取平均。
    rain 非空时只对雨区格点参与均值（弱回波不拉偏）。
    """
    u = np.asarray(u, float)
    v = np.asarray(v, float)
    nlat, nlon = u.shape
    num_x = max(int(win_deg / dlon), 1)
    num_y = max(int(win_deg / dlat), 1)
    pdx = max(int(0.5 * num_x), 1)
    pdy = max(int(0.5 * num_y), 1)
    x_index = list(range(int(0.5 * num_x) + 1, nlon, pdx))
    y_index = list(range(int(0.5 * num_y) + 1, nlat, pdy))

    if rain is None:
        mask_rain = np.ones_like(u, dtype=bool)
    else:
        mask_rain = np.asarray(rain, float) >= rain_limit

    sum_u = np.zeros_like(u)
    sum_v = np.zeros_like(v)
    cnt = np.zeros_like(u, dtype=float)

    for j0 in y_index:
        for i0 in x_index:
            jj = np.arange(j0 - pdy, j0 + pdy + 1)
            ii = np.arange(i0 - pdx, i0 + pdx + 1)
            jj = jj[(jj >= 0) & (jj < nlat)]
            ii = ii[(ii >= 0) & (ii < nlon)]
            yy, xx = np.meshgrid(jj, ii, indexing="ij")
            m = mask_rain[yy, xx]
            if not np.any(m):
                continue
            mu = float(np.mean(u[yy, xx][m]))
            mv = float(np.mean(v[yy, xx][m]))
            sum_u[yy, xx] += mu
            sum_v[yy, xx] += mv
            cnt[yy, xx] += 1.0

    out_u = np.where(cnt > 0, sum_u / cnt, u)
    out_v = np.where(cnt > 0, sum_v / cnt, v)
    return out_u, out_v


def apply_gain(u, v, gain_u, gain_v=None):
    gv = gain_u if gain_v is None else gain_v
    return np.asarray(u, float) * float(gain_u), np.asarray(v, float) * float(gv)


def safe_gain(pred_mean, ref_mean, eps=1e-8):
    if abs(pred_mean) < eps:
        return 1.0
    return float(ref_mean / pred_mean)


# ---------- 评分 ----------

def field_stats(pred, ref):
    d = np.asarray(pred, float) - np.asarray(ref, float)
    return {
        "meanAbs": float(np.mean(np.abs(d))),
        "rmse": float(np.sqrt(np.mean(d * d))),
        "mean_pred": float(np.mean(pred)),
        "mean_ref": float(np.mean(ref)),
        "bias": float(np.mean(pred) - np.mean(ref)),
    }


def truth_stats(pred, true_u, true_v):
    """均匀真值场：看全域均值偏差与相对真值场的 rmse。"""
    u, v = pred
    tu = np.full_like(u, true_u)
    tv = np.full_like(v, true_v)
    return {
        "u_mean": float(np.mean(u)),
        "v_mean": float(np.mean(v)),
        "u_bias": float(np.mean(u) - true_u),
        "v_bias": float(np.mean(v) - true_v),
        "u_rmse": field_stats(u, tu)["rmse"],
        "v_rmse": field_stats(v, tv)["rmse"],
    }


def fmt_vs_of(tag, su, sv):
    return (f"{tag:18s}  vsOF  u: meanAbs={su['meanAbs']:.4f} rmse={su['rmse']:.4f} "
            f"mean={su['mean_pred']:.4f} (OF={su['mean_ref']:.4f})  |  "
            f"v: meanAbs={sv['meanAbs']:.4f} rmse={sv['rmse']:.4f}")


def fmt_vs_truth(tag, t):
    return (f"{tag:18s}  vs真值 u_mean={t['u_mean']:.4f} bias={t['u_bias']:+.4f} "
            f"rmse={t['u_rmse']:.4f}  |  "
            f"v_mean={t['v_mean']:.4f} bias={t['v_bias']:+.4f} rmse={t['v_rmse']:.4f}")


# ---------- 主流程 ----------

# 多组合成位移（度/步）
CASES = [
    (0.1, 0.0),
    (0.2, 0.0),
    (0.3, 0.0),
    (0.5, 0.0),
    (0.3, 0.1),
    (0.3, -0.1),
    (-0.2, 0.0),
]


def run_one(true_u, true_v, win_deg=5.0):
    before, nxt, dlon, tu, tv, lon, lat = make_pair(true_u_deg=true_u, true_v_deg=true_v)
    rain = arr(before)

    u_of, v_of = run_opticalflow(before, nxt, min_window=(win_deg, win_deg))
    u_px, v_px = run_lk(before, nxt)

    # B0: 仅换算
    u0 = u_px * dlon
    v0 = v_px * dlon
    # B1: 窗聚合（雨区参与均值）
    u1, v1 = window_aggregate(u0, v0, dlon, dlon, win_deg=win_deg, rain=rain, rain_limit=1.0)
    # B2: 逐案 gain 贴 OF 均值
    gu = safe_gain(np.mean(u1), np.mean(u_of))
    gv = safe_gain(np.mean(v1), np.mean(v_of))
    u2, v2 = apply_gain(u1, v1, gu, gv)

    variants = {
        "B0 LK→度": (u0, v0),
        "B1 +窗聚合": (u1, v1),
        "B2 +窗+案gain": (u2, v2),
    }
    return {
        "true_u": tu, "true_v": tv, "dlon": dlon,
        "lon": lon, "lat": lat,
        "of": (u_of, v_of),
        "variants": variants,
        "case_gain": (gu, gv),
        "means": {
            "of_u": float(np.mean(u_of)), "of_v": float(np.mean(v_of)),
            "b1_u": float(np.mean(u1)), "b1_v": float(np.mean(v1)),
        },
    }


def main():
    win_deg = 5.0
    print("=" * 78)
    print(f"LK 适配试验：度换算 → {win_deg}° 窗聚合 → 可选 gain")
    print(f"合成位移组数: {len(CASES)}")
    print("=" * 78)

    results = []
    for tu, tv in CASES:
        print(f"\n--- 真值 u={tu}°  v={tv}° ---")
        try:
            r = run_one(tu, tv, win_deg=win_deg)
        except Exception as e:
            print(f"  失败: {e}")
            continue
        results.append(r)
        u_of, v_of = r["of"]
        print(f"  OF mean u={r['means']['of_u']:.4f}  v={r['means']['of_v']:.4f}")
        print(f"  案 gain(u,v)=({r['case_gain'][0]:.3f}, {r['case_gain'][1]:.3f})")
        for name, (uu, vv) in r["variants"].items():
            su = field_stats(uu, u_of)
            sv = field_stats(vv, v_of)
            print(" ", fmt_vs_of(name, su, sv))
            print(" ", fmt_vs_truth(name, truth_stats((uu, vv), tu, tv)))

    if not results:
        print("无成功算例，退出。")
        return

    # 跨案全局 gain：用所有案的 mean(B1) 对 mean(OF) 做比例（过原点）
    b1u = np.array([r["means"]["b1_u"] for r in results])
    ofu = np.array([r["means"]["of_u"] for r in results])
    b1v = np.array([r["means"]["b1_v"] for r in results])
    ofv = np.array([r["means"]["of_v"] for r in results])
    # 最小二乘过原点：gain = Σ p·r / Σ p²
    def fit_gain(pred, ref):
        den = float(np.dot(pred, pred))
        return 1.0 if den < 1e-12 else float(np.dot(pred, ref) / den)

    g_global_u = fit_gain(b1u, ofu)
    g_global_v = fit_gain(b1v, ofv)
    print("\n" + "=" * 78)
    print(f"跨案全局 gain（B1→OF, 过原点 LS）: u×{g_global_u:.3f}  v×{g_global_v:.3f}")

    # 用全局 gain 重算各案，汇总表
    rows = []
    for r in results:
        u_of, v_of = r["of"]
        tu, tv = r["true_u"], r["true_v"]
        u1, v1 = r["variants"]["B1 +窗聚合"]
        ug, vg = apply_gain(u1, v1, g_global_u, g_global_v)
        pack = {
            "B0": r["variants"]["B0 LK→度"],
            "B1": (u1, v1),
            "B2案": r["variants"]["B2 +窗+案gain"],
            "B2全局": (ug, vg),
            "OF": (u_of, v_of),
        }
        row = {"true_u": tu, "true_v": tv}
        for k, (uu, vv) in pack.items():
            su = field_stats(uu, u_of)
            tt = truth_stats((uu, vv), tu, tv)
            row[f"{k}_vsOF_u"] = su["meanAbs"]
            row[f"{k}_vs真_u_bias"] = tt["u_bias"]
            row[f"{k}_vs真_u_rmse"] = tt["u_rmse"]
        rows.append(row)

    # 汇总：各适配相对 OF / 真值 的平均 |bias| 与 meanAbs
    print("\n汇总（各案平均）:")
    hdr = f"{'适配':12s}  {'vsOF meanAbs(u)':>16s}  {'vs真 |bias(u)|':>14s}  {'vs真 rmse(u)':>12s}"
    print(hdr)
    print("-" * len(hdr))
    for key, label in [
        ("B0", "B0 仅换算"),
        ("B1", "B1 +窗聚合"),
        ("B2案", "B2 案gain"),
        ("B2全局", "B2 全局gain"),
        ("OF", "OF(对照)"),
    ]:
        m_of = np.mean([row[f"{key}_vsOF_u"] for row in rows])
        m_bias = np.mean([abs(row[f"{key}_vs真_u_bias"]) for row in rows])
        m_rmse = np.mean([row[f"{key}_vs真_u_rmse"] for row in rows])
        print(f"{label:12s}  {m_of:16.4f}  {m_bias:14.4f}  {m_rmse:12.4f}")

    print("\n说明:")
    print("  · vsOF 变小 = 更贴原版产品；vs真 变小 = 物理更准。")
    print("  · 若 B2 贴 OF 变好、贴真值变差 → gain 在追 OF 的偏差，慎用于业务。")
    print("  · B1 相对 B0：看窗聚合是否只改结构、对均值影响多大。")
    print("=" * 78)

    # 图：取真值 (0.3, 0) 一案，画 B0/B1/B2/OF 的 u
    pick = next((r for r in results if abs(r["true_u"] - 0.3) < 1e-9 and abs(r["true_v"]) < 1e-9), results[0])
    import matplotlib.pyplot as plt

    lon, lat = pick["lon"], pick["lat"]
    u_of, _ = pick["of"]
    u0, _ = pick["variants"]["B0 LK→度"]
    u1, _ = pick["variants"]["B1 +窗聚合"]
    u2, _ = pick["variants"]["B2 +窗+案gain"]
    u_g, _ = apply_gain(u1, np.zeros_like(u1), g_global_u, 1.0)

    panels = [
        ("OF u", u_of),
        ("B0 LK→度", u0),
        ("B1 +窗聚合", u1),
        ("B2 案gain", u2),
        ("B2 全局gain", u_g),
        ("B1−OF", u1 - u_of),
    ]
    umax = max(np.max(np.abs(p[1])) for p in panels[:5]) + 1e-6
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for ax, (title, field) in zip(axes.ravel(), panels):
        if "−" in title or "-" in title:
            vmax = max(np.max(np.abs(field)), 1e-3)
            im = ax.pcolormesh(lon, lat, field, shading="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
        else:
            im = ax.pcolormesh(lon, lat, field, shading="auto", cmap="RdBu_r", vmin=-umax, vmax=umax)
        ax.set_title(title, fontsize=11)
        ax.set_aspect("equal")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle(
        f"LK 适配 vs OF（真值 u={pick['true_u']}°, v={pick['true_v']}°；全局gain_u={g_global_u:.3f}）",
        fontsize=13,
    )
    png = os.path.join(HERE, "demo_lk_adapt_vs_of.png")
    fig.savefig(png, dpi=130)
    print(f"图: {png}")


if __name__ == "__main__":
    main()
