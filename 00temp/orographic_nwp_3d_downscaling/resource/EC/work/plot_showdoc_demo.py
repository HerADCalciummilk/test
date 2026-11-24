#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Plot EC site trial: model 2t at stations (before) vs refined h5 (after)."""

from __future__ import annotations

from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import meteva_base as meb
import numpy as np
import pandas as pd
import xarray as xr
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from meteva_base.tool.plot_tools import pcolormesh_2d_grid, scatter_sta
from scipy.interpolate import RegularGridInterpolator

EC = Path(__file__).resolve().parents[1]
OUT_DIR = EC / "work" / "showdoc_figs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TMP2M = EC / "TMP_2M" / "2026" / "20260728" / "2026072800.006.nc"
H5 = (
    EC
    / "output"
    / "3PreProcess"
    / "g_interp"
    / "EC_12P5KM"
    / "Site"
    / "2026"
    / "20260728"
    / "08"
    / "006_006.h5"
)
STATION = EC / "Parameter" / "Station1"


def read_stations(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    rows = []
    for line in lines[1:]:
        parts = line.split()
        rows.append(
            {
                "id": parts[0],
                "name": parts[1],
                "lon": float(parts[2]),
                "lat": float(parts[3]),
                "alt": float(parts[4]),
            }
        )
    return pd.DataFrame(rows)


def sample_grid(nc_path: Path, lons, lats) -> np.ndarray:
    ds = xr.open_dataset(nc_path)
    lon = ds["lon"].values.astype(float)
    lat = ds["lat"].values.astype(float)
    data = np.asarray(ds["data0"].values, dtype=float).squeeze()
    # RegularGridInterpolator expects ascending axes
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        data = data[::-1, :]
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        data = data[:, ::-1]
    # Kelvin → ℃ if needed
    if np.nanmean(data) > 200:
        data = data - 273.15
    interp = RegularGridInterpolator((lat, lon), data, bounds_error=False, fill_value=np.nan)
    pts = np.column_stack([lats, lons])
    out = interp(pts)
    ds.close()
    return out


def sta_from_values(df: pd.DataFrame, values: np.ndarray, time_str: str = "2026-07-28 14:00:00"):
    """Build meteva station DataFrame for scatter_sta."""
    data = {
        "level": [0] * len(df),
        "time": [pd.Timestamp(time_str)] * len(df),
        "dtime": [0] * len(df),
        "id": df["id"].astype(int).tolist(),
        "lon": df["lon"].tolist(),
        "lat": df["lat"].tolist(),
        "data0": values.tolist(),
    }
    return pd.DataFrame(data)


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    df = read_stations(STATION)
    with h5py.File(H5, "r") as f:
        sites = [x.decode() if isinstance(x, bytes) else str(x) for x in f["site"][:]]
        t_after = np.asarray(f["2t"][:], dtype=float)
        gamma = np.asarray(f["gamma_2t"][:], dtype=float)
    # align order to Station1
    order = [sites.index(sid) for sid in df["id"].astype(str)]
    t_after = t_after[order]
    gamma = gamma[order]
    t_before = sample_grid(TMP2M, df["lon"].values, df["lat"].values)

    print("site comparison (℃):")
    for i, row in df.iterrows():
        d = t_after[i] - t_before[i]
        print(
            f"  {row['id']} {row['name']}: before={t_before[i]:.2f} after={t_after[i]:.2f} "
            f"dT={d:+.2f} gamma={gamma[i]:.5f} alt={row['alt']:.1f}m"
        )

    cmap, clevs = get_cmap_and_clevs_by_element_name("temp")
    # summer day: focus color levels around observed range
    clevs_use = [c for c in clevs if 16 <= c <= 40]
    if len(clevs_use) < 6:
        clevs_use = clevs

    # 1) input grid field
    grd = meb.read_griddata_from_nc(str(TMP2M))
    if float(np.nanmean(grd.values)) > 200:
        grd = grd - 273.15
    p_in = OUT_DIR / "ec_tmp2m_input.png"
    pcolormesh_2d_grid(
        grd,
        save_path=str(p_in),
        title="EC TMP_2M 输入场（℃，0.1°，UTC 00+006）",
        cmap=cmap,
        clevs=clevs_use,
        show=False,
    )
    print("wrote", p_in)

    # 2) before/after station scatter（含高原站，图幅需覆盖拉萨）
    map_extend = [85, 130, 20, 48]
    sta_b = sta_from_values(df, t_before)
    sta_a = sta_from_values(df, t_after)

    # 单场 scatter_sta：处理前 / 处理后（共用色标）
    p_before = OUT_DIR / "ec_site_2t_before.png"
    p_after = OUT_DIR / "ec_site_2t_after.png"
    scatter_sta(
        sta_b,
        save_path=str(p_before),
        title="处理前站点 2t（℃）- 模式场双线性取样",
        cmap=cmap,
        clevs=clevs_use,
        map_extend=map_extend,
        show=False,
    )
    scatter_sta(
        sta_a,
        save_path=str(p_after),
        title="处理后站点 2t（℃）- 三维精细化插值",
        cmap=cmap,
        clevs=clevs_use,
        map_extend=map_extend,
        show=False,
    )

    # 对照图：creat_axs + 手动 scatter（保证同色标、6 站都可见）
    axs = meb.creat_axs(
        2,
        map_extend,
        ncol=2,
        title_list=["处理前（模式场双线性取样）", "处理后（三维精细化插值）"],
        add_worldmap=False,
        add_index=True,
        wspace=0.15,
        width=14,
        height=5.8,
    )
    # 用 meteva 色标对应的 ListedColormap
    try:
        from matplotlib.colors import BoundaryNorm, ListedColormap

        if hasattr(cmap, "colors"):
            listed = ListedColormap(cmap.colors)
        else:
            listed = plt.get_cmap("RdYlBu_r")
        norm = BoundaryNorm(clevs_use, listed.N)
    except Exception:
        listed = plt.get_cmap("RdYlBu_r")
        norm = None
    for ax, vals in ((axs[0], t_before), (axs[1], t_after)):
        sc = ax.scatter(
            df["lon"],
            df["lat"],
            c=vals,
            s=140,
            cmap=listed,
            norm=norm,
            edgecolors="k",
            linewidths=0.6,
            zorder=5,
        )
        for i, row in df.iterrows():
            ax.annotate(
                f"{row['name']} {vals[i]:.1f}",
                (row["lon"], row["lat"]),
                textcoords="offset points",
                xytext=(5, 5),
                fontsize=8,
            )
        plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, ticks=clevs_use)
    p_cmp = OUT_DIR / "ec_site_2t_before_after.png"
    plt.savefig(p_cmp, dpi=150, bbox_inches="tight")
    plt.close("all")
    print("wrote", p_cmp)
    print("wrote", p_before)
    print("wrote", p_after)
    print("done")


if __name__ == "__main__":
    main()
