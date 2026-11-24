#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Grid-1km regional verify: bi (model→1km) vs lr (refined) vs HRCLDAS obs."""

from __future__ import annotations

from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import meteva_base as meb
import numpy as np
import xarray as xr
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
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
THRESH = 2.0


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    ds_o = xr.open_dataset(OBS)
    lat = ds_o["lat"].values.astype(float)
    lon = ds_o["lon"].values.astype(float)
    obs = np.asarray(ds_o["data0"].values, dtype=float)
    ds_o.close()

    with h5py.File(H5, "r") as f:
        print("h5 keys", list(f.keys()))
        lr = np.asarray(f["2t"][...], dtype=float)
        if lr.ndim > 2:
            lr = np.squeeze(lr)
        # match orientation: algorithm stores south-north?
        print("lr shape", lr.shape, "obs", obs.shape)

    # bilinear from coarse model onto fine grid
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

    # align lr shape/orientation to obs (lat ascending south→north)
    if lr.shape != obs.shape:
        # try flip
        if lr.shape == obs.shape[::-1]:
            lr = lr.T
        elif lr[::-1, :].shape == obs.shape:
            lr = lr[::-1, :]
        else:
            raise SystemExit(f"shape mismatch lr{lr.shape} obs{obs.shape}")
    # if correlation better when flipped
    def corr(a, b):
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 10:
            return -1
        return float(np.corrcoef(a[m], b[m])[0, 1])

    if corr(lr[::-1, :], obs) > corr(lr, obs) + 0.05:
        lr = lr[::-1, :]
        print("flipped lr N-S for alignment")

    fill = -32766.0
    lr = np.where(np.abs(lr - fill) < 1, np.nan, lr)
    mask = np.isfinite(obs) & np.isfinite(bi) & np.isfinite(lr)

    def stats(pred):
        d = pred[mask] - obs[mask]
        ae = np.abs(d)
        return {
            "n": int(mask.sum()),
            "bias": float(np.mean(d)),
            "rmse": float(np.sqrt(np.mean(d**2))),
            "mae": float(np.mean(ae)),
            "hit": float((ae <= THRESH).sum() / mask.sum()),
        }

    sb, sa = stats(bi), stats(lr)
    print("=== regional 1km vs HRCLDAS (90–108E / 25–38N) ===")
    print(f"bi  n={sb['n']} bias={sb['bias']:+.3f} rmse={sb['rmse']:.3f} mae={sb['mae']:.3f} hit={sb['hit']:.3f}")
    print(f"lr  n={sa['n']} bias={sa['bias']:+.3f} rmse={sa['rmse']:.3f} mae={sa['mae']:.3f} hit={sa['hit']:.3f}")
    print(f"delta_rmse(lr-bi)={sa['rmse']-sb['rmse']:+.3f}")

    cmap, clevs = get_cmap_and_clevs_by_element_name("temp")
    clevs_use = [c for c in clevs if 0 <= c <= 40]

    def to_grd(arr, name):
        return meb.grid_data(
            meb.grid([float(lon[0]), float(lon[-1]), float(lon[1] - lon[0])],
                     [float(lat[0]), float(lat[-1]), float(lat[1] - lat[0])]),
            arr,
        )

    for arr, title, fn in (
        (bi, "订正前-模式双线性到1km（℃）", "case1km_before.png"),
        (lr, "订正后-三维精细化1km（℃）", "case1km_after.png"),
        (obs, "实况-HRCLDAS取样到1km（℃）", "case1km_obs.png"),
    ):
        grd = to_grd(arr, title)
        pcolormesh_2d_grid(
            grd,
            save_path=str(OUT / fn),
            title=title,
            cmap=cmap,
            clevs=clevs_use,
            show=False,
        )
        print("wrote", OUT / fn)

    # difference panel
    diff = lr - bi
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.2), constrained_layout=True)
    for ax, data, t, vmin, vmax, cmapx in (
        (axs[0], bi, "订正前 bi", 0, 40, "RdYlBu_r"),
        (axs[1], lr, "订正后 lr", 0, 40, "RdYlBu_r"),
        (axs[2], diff, "lr−bi", -5, 5, "bwr"),
    ):
        im = ax.pcolormesh(lon, lat, data, shading="auto", cmap=cmapx, vmin=vmin, vmax=vmax)
        ax.set_title(t)
        ax.set_aspect("equal")
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.suptitle("川西–藏东 1km 个例（90–108E / 25–38N）2t ℃")
    p = OUT / "case1km_before_after_diff.png"
    fig.savefig(p, dpi=140)
    plt.close(fig)
    print("wrote", p)

    # save metrics
    (EC / "work" / "verify_1km_metrics.txt").write_text(
        f"bi bias={sb['bias']:+.3f} rmse={sb['rmse']:.3f} mae={sb['mae']:.3f} hit={sb['hit']:.3f}\n"
        f"lr bias={sa['bias']:+.3f} rmse={sa['rmse']:.3f} mae={sa['mae']:.3f} hit={sa['hit']:.3f}\n"
        f"delta_rmse={sa['rmse']-sb['rmse']:+.3f}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
