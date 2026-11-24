#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Make ShowDoc 1km regional before/after panels (creat_axs + add_contourf)."""

from __future__ import annotations

from pathlib import Path

import h5py
import meteva_base as meb
import numpy as np
import xarray as xr
from matplotlib import pyplot as plt
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from scipy.interpolate import RegularGridInterpolator

EC = Path(__file__).resolve().parents[1]
OUT = EC / "work" / "showdoc_figs"
OUT.mkdir(parents=True, exist_ok=True)

H5 = (
    EC
    / "output"
    / "3PreProcess"
    / "g_interp"
    / "EC_12P5KM"
    / "Grid_1km"
    / "2026"
    / "20260728"
    / "08"
    / "006_006.h5"
)
OBS = EC / "Grid_1km" / "Hourly" / "TMP_2M" / "2026" / "20260728" / "BJT_2026072814.000.nc"
TMP2M = EC / "TMP_2M" / "2026" / "20260728" / "2026072800.006.nc"


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    ds_o = xr.open_dataset(OBS)
    lat = ds_o["lat"].values.astype(float)
    lon = ds_o["lon"].values.astype(float)
    obs = np.asarray(ds_o["data0"].values, dtype=float)
    ds_o.close()

    with h5py.File(H5, "r") as f:
        lr = np.asarray(f["2t"][...], dtype=float)
        ll = np.asarray(f["lon_lat"][...], dtype=float)

    # h5 is S→N (same as obs NC); algorithm in-memory uses N→S
    ds_m = xr.open_dataset(TMP2M)
    mlat = ds_m["lat"].values.astype(float)
    mlon = ds_m["lon"].values.astype(float)
    mdl = np.asarray(ds_m["data0"].values, dtype=float).squeeze()
    if np.nanmean(mdl) > 200:
        mdl = mdl - 273.15
    if mlat[0] > mlat[-1]:
        mlat = mlat[::-1]
        mdl = mdl[::-1, :]
    interp = RegularGridInterpolator((mlat, mlon), mdl, bounds_error=False, fill_value=np.nan)
    yy, xx = np.meshgrid(lat, lon, indexing="ij")
    bi = interp(np.column_stack([yy.ravel(), xx.ravel()])).reshape(obs.shape)
    ds_m.close()

    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])
    grid = meb.grid([float(lon[0]), float(lon[-1]), dlon], [float(lat[0]), float(lat[-1]), dlat])
    grd_bi = meb.grid_data(grid, bi)
    grd_lr = meb.grid_data(grid, lr)
    grd_obs = meb.grid_data(grid, obs)

    cmap, clevs = get_cmap_and_clevs_by_element_name("temp")
    clevs_use = [c for c in clevs if -5 <= c <= 40]
    map_extend = [float(ll[0]), float(ll[1]), float(ll[2]), float(ll[3])]

    axs = meb.creat_axs(
        2,
        map_extend,
        ncol=2,
        title_list=["订正前 bi（模式→1km 双线性）", "订正后 lr（三维精细化 1km）"],
        add_worldmap=False,
        add_index=True,
        width=12,
        height=5.2,
    )
    meb.add_contourf(axs[0], grd_bi, cmap=cmap, clevs=clevs_use, cut_colorbar=False, add_colorbar=True)
    meb.add_contourf(axs[1], grd_lr, cmap=cmap, clevs=clevs_use, cut_colorbar=False, add_colorbar=True)
    p1 = OUT / "case1km_before_after.png"
    plt.savefig(p1, dpi=140, bbox_inches="tight")
    plt.close("all")
    print("wrote", p1)

    # obs alone for optional third
    from meteva_base.tool.plot_tools import pcolormesh_2d_grid

    pcolormesh_2d_grid(
        grd_obs,
        save_path=str(OUT / "case1km_obs.png"),
        title="实况 HRCLDAS→1km（℃）",
        cmap=cmap,
        clevs=clevs_use,
        show=False,
    )
    pcolormesh_2d_grid(
        grd_bi,
        save_path=str(OUT / "case1km_before.png"),
        title="订正前 bi（℃）",
        cmap=cmap,
        clevs=clevs_use,
        show=False,
    )
    pcolormesh_2d_grid(
        grd_lr,
        save_path=str(OUT / "case1km_after.png"),
        title="订正后 lr（℃）",
        cmap=cmap,
        clevs=clevs_use,
        show=False,
    )
    print("lon_lat", ll, "shapes", bi.shape, lr.shape)


if __name__ == "__main__":
    main()
