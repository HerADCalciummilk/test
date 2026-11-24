# -*- coding: utf-8 -*-
"""
针对「靠边不一致」多组复现，并试再处理能否抹平。

已知：域内有限格点两边几乎相同；差出在 Extrapolation 出界=nan，
Lagrangian 夹索引后仍双线性（甚至可能算出负雨）。

再处理方案：
  P0  Extrapolation nan→0 再比（旧做法）
  P1  Extrapolation nan 格改用与 Lagrangian 相同的「夹边双线性」回填
  P2  两边凡后向点出界的格都置 0（更合理的业务边界）

运行::
    python demo_advection_boundary_fix.py
"""
from __future__ import annotations

import os
import sys
types_mod = __import__("types")
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAIN_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
OF_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "optical_flow_nowcast"))

sys.path.insert(0, RAIN_SRC)
sys.modules["utils"] = types_mod.ModuleType("utils")
sys.modules["utils"].__path__ = [os.path.join(RAIN_SRC, "utils")]
from frequency_matching_rain24_plugin import Lagrangian  # noqa: E402

sys.path.insert(0, OF_ROOT)
from src.extrapolation_plugin import forecast as extrap_forecast  # noqa: E402

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


def uv_const(rain, u_deg, v_deg):
    a = arr(rain)
    u, v = rain.copy(), rain.copy()
    u.data = [[[[np.full_like(a, u_deg)]]]]
    v.data = [[[[np.full_like(a, v_deg)]]]]
    return u, v


def run_extrap(precip, u_deg, v_deg):
    vel = np.stack([
        np.full_like(precip, u_deg / DLON),
        np.full_like(precip, v_deg / DLAT),
    ], axis=0)
    out = np.asarray(extrap_forecast(precip, vel, 1)[0], dtype=float)
    return out


def clamp_bilinear(precip, u_deg, v_deg, lon, lat):
    """与原版 Lagrangian 相同：偏移后索引 clip，再双线性（出界也会算）。"""
    nlat, nlon = precip.shape
    lon2d, lat2d = np.meshgrid(lon, lat)
    lon_off = lon2d - u_deg
    lat_off = lat2d - v_deg
    slon, slat = lon[0], lat[0]
    i1 = np.clip(((lon_off - slon) / DLON).astype(int), 0, nlon - 2)
    j1 = np.clip(((lat_off - slat) / DLAT).astype(int), 0, nlat - 2)
    wlon1 = (lon[i1 + 1] - lon_off) / DLON
    wlon2 = (lon_off - lon[i1]) / DLON
    wlat1 = (lat[j1 + 1] - lat_off) / DLAT
    wlat2 = (lat_off - lat[j1]) / DLAT
    return (
        wlon1 * (wlat1 * precip[j1, i1] + wlat2 * precip[j1 + 1, i1])
        + wlon2 * (wlat1 * precip[j1, i1 + 1] + wlat2 * precip[j1 + 1, i1 + 1])
    )


def oob_mask(u_deg, v_deg, lon, lat):
    """后向取样点是否出域。"""
    lon2d, lat2d = np.meshgrid(lon, lat)
    lon_off = lon2d - u_deg
    lat_off = lat2d - v_deg
    return (
        (lon_off < lon[0]) | (lon_off > lon[-1])
        | (lat_off < lat[0]) | (lat_off > lat[-1])
    )


def metrics(a, b):
    d = a - b
    return float(np.mean(np.abs(d))), float(np.max(np.abs(d)))


def one_case(name, lon0, lat0, u_deg, v_deg):
    rain, lon, lat = make_blob(lon0, lat0)
    precip = arr(rain)
    u, v = uv_const(rain, u_deg, v_deg)

    out_l = arr(Lagrangian.simple_semi_lagrangian_in_angle(u, v, rain, 1.0))
    out_e = run_extrap(precip, u_deg, v_deg)
    nan_m = ~np.isfinite(out_e)
    oob = oob_mask(u_deg, v_deg, lon, lat)

    # P0: nan→0
    e0 = np.where(nan_m, 0.0, out_e)
    m0, x0 = metrics(e0, out_l)

    # P1: nan 用夹边双线性回填（对齐 Lagrangian 边界行为）
    fill = clamp_bilinear(precip, u_deg, v_deg, lon, lat)
    e1 = np.where(nan_m, fill, out_e)
    m1, x1 = metrics(e1, out_l)

    # P2: 两边出界都置 0
    l2 = np.where(oob, 0.0, out_l)
    e2 = np.where(oob | nan_m, 0.0, out_e)
    m2, x2 = metrics(e2, l2)

    # 域内有限格（非 nan）差
    if np.any(~nan_m):
        mi, xi = metrics(out_e[~nan_m], out_l[~nan_m])
    else:
        mi, xi = 0.0, 0.0

    return {
        "name": name,
        "n_nan": int(nan_m.sum()),
        "n_oob": int(oob.sum()),
        "fin_maxAbs": xi,
        "P0_maxAbs": x0,
        "P1_maxAbs": x1,
        "P2_maxAbs": x2,
        "P0_ok": x0 < 1e-5,
        "P1_ok": x1 < 1e-5,
        "P2_ok": x2 < 1e-5,
    }


def main():
    # 多组：角落/靠边 + 不同位移方向与大小
    cases = [
        ("西南角 东移0.3", 110.6, 33.6, 0.3, 0.0),
        ("西南角 东移0.5", 110.6, 33.6, 0.5, 0.0),
        ("西南角 东移1.0", 110.6, 33.6, 1.0, 0.0),
        ("西南角 北移0.3", 110.6, 33.6, 0.0, 0.3),
        ("西南角 东北0.3", 110.6, 33.6, 0.3, 0.3),
        ("东南角 西移0.3", 113.4, 33.6, -0.3, 0.0),
        ("西北角 南移0.3", 110.6, 36.4, 0.0, -0.3),
        ("东北角 西南0.3", 113.4, 36.4, -0.3, -0.3),
        ("西缘中 东移0.3", 110.5, 35.0, 0.3, 0.0),
        ("南缘中 北移0.3", 112.0, 33.5, 0.0, 0.3),
        ("西南角 西移0.3(更出界)", 110.6, 33.6, -0.3, 0.0),
        ("重复1 西南东移0.3", 110.6, 33.6, 0.3, 0.0),
        ("重复2 西南东移0.3", 110.6, 33.6, 0.3, 0.0),
        ("重复3 西南东移0.3", 110.6, 33.6, 0.3, 0.0),
    ]

    print("=" * 88)
    print("靠边用例复现 + 再处理")
    print(f"{'用例':<22} {'nan':>4} {'域内max':>10} "
          f"{'P0填0':>10} {'P1夹边回填':>10} {'P2出界置0':>10}")
    print("-" * 88)

    rows = [one_case(*c) for c in cases]
    for r in rows:
        print(
            f"{r['name']:<22} {r['n_nan']:4d} {r['fin_maxAbs']:10.2e} "
            f"{r['P0_maxAbs']:10.4f} {r['P1_maxAbs']:10.4f} {r['P2_maxAbs']:10.4f}"
        )

    def rate(key):
        return sum(1 for r in rows if r[key]) / len(rows)

    print("-" * 88)
    print(f"完全一致比例: P0(nan→0)={rate('P0_ok'):.0%}  "
          f"P1(夹边回填)={rate('P1_ok'):.0%}  P2(出界置0)={rate('P2_ok'):.0%}")
    print()
    print("解读：")
    print("  · 域内max≈0 → 不一致不是算错 UV，只在出界格。")
    print("  · P1：用 Lagrangian 同款夹边双线性填 Extrapolation 的 nan → 可与原版对齐。")
    print("  · P2：两边出界都置 0 → 也一致，且避免 Lagrangian 出界算出负雨。")
    print("  · 推荐业务：Extrapolation 后对出界用 P2；若必须咬死原版边界行为用 P1。")
    print("=" * 88)


if __name__ == "__main__":
    main()
