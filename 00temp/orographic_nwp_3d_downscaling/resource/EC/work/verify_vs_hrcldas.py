#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify site 2t product against HRCLDAS gridded Tair (sampled to stations)."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

EC = Path(__file__).resolve().parents[1]
RES = EC.parent
STATION = EC / "Parameter" / "Station1"
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
OBS_DIR = RES / "hrcldas_tair" / "2026" / "20260728"


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


def sample_nc(nc_path: Path, lons, lats) -> np.ndarray:
    ds = xr.open_dataset(nc_path)
    lon = ds["lon"].values.astype(float)
    lat = ds["lat"].values.astype(float)
    data = np.asarray(ds["data0"].values, dtype=float).squeeze()
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        data = data[::-1, :]
    if np.nanmean(data) > 200:
        data = data - 273.15
    interp = RegularGridInterpolator((lat, lon), data, bounds_error=False, fill_value=np.nan)
    out = interp(np.column_stack([lats, lons]))
    ds.close()
    return out


def sample_hrcldas(grb_path: Path, lons, lats) -> np.ndarray:
    ds = xr.open_dataset(grb_path, engine="cfgrib")
    lon = ds["longitude"].values.astype(float)
    lat = ds["latitude"].values.astype(float)
    data = np.asarray(ds["t2m"].values, dtype=float)
    # K -> C
    if np.nanmean(data) > 200:
        data = data - 273.15
    # latitude often ascending 0->60
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        data = data[::-1, :]
    interp = RegularGridInterpolator((lat, lon), data, bounds_error=False, fill_value=np.nan)
    out = interp(np.column_stack([lats, lons]))
    ds.close()
    return out


def metrics(pred: np.ndarray, obs: np.ndarray) -> dict:
    mask = np.isfinite(pred) & np.isfinite(obs)
    d = pred[mask] - obs[mask]
    return {
        "n": int(mask.sum()),
        "bias": float(np.mean(d)) if mask.any() else np.nan,
        "rmse": float(np.sqrt(np.mean(d**2))) if mask.any() else np.nan,
        "mae": float(np.mean(np.abs(d))) if mask.any() else np.nan,
    }


def main() -> None:
    grbs = sorted(OBS_DIR.glob("*.GRB2")) + sorted(OBS_DIR.glob("*.grb2"))
    if not grbs:
        raise FileNotFoundError(f"no GRB2 under {OBS_DIR}")
    obs_file = grbs[0]
    print("obs:", obs_file.name)

    df = read_stations(STATION)
    with h5py.File(H5, "r") as f:
        sites = [x.decode() if isinstance(x, bytes) else str(x) for x in f["site"][:]]
        t_after = np.asarray(f["2t"][:], dtype=float)
    order = [sites.index(sid) for sid in df["id"].astype(str)]
    t_after = t_after[order]
    t_before = sample_nc(TMP2M, df["lon"].values, df["lat"].values)
    t_obs = sample_hrcldas(obs_file, df["lon"].values, df["lat"].values)

    print(
        f"{'id':>6} {'name':<10} {'alt':>7} {'obs':>7} {'before':>7} {'after':>7} "
        f"{'b-o':>7} {'a-o':>7}"
    )
    for i, row in df.iterrows():
        print(
            f"{row['id']:>6} {row['name']:<10} {row['alt']:7.1f} {t_obs[i]:7.2f} "
            f"{t_before[i]:7.2f} {t_after[i]:7.2f} "
            f"{t_before[i]-t_obs[i]:+7.2f} {t_after[i]-t_obs[i]:+7.2f}"
        )

    mb = metrics(t_before, t_obs)
    ma = metrics(t_after, t_obs)
    print("\n=== vs HRCLDAS (station-sampled), unit C ===")
    print(f"before (bilinear): n={mb['n']} bias={mb['bias']:+.3f} rmse={mb['rmse']:.3f} mae={mb['mae']:.3f}")
    print(f"after  (refined) : n={ma['n']} bias={ma['bias']:+.3f} rmse={ma['rmse']:.3f} mae={ma['mae']:.3f}")
    print(f"delta_rmse (after-before)={ma['rmse']-mb['rmse']:+.3f}  (negative = improved)")

    out_csv = Path(__file__).resolve().parent / "verify_vs_hrcldas.csv"
    pd.DataFrame(
        {
            "id": df["id"],
            "name": df["name"],
            "alt": df["alt"],
            "lon": df["lon"],
            "lat": df["lat"],
            "obs": t_obs,
            "before": t_before,
            "after": t_after,
            "err_before": t_before - t_obs,
            "err_after": t_after - t_obs,
        }
    ).to_csv(out_csv, index=False, float_format="%.3f")
    print("wrote", out_csv)


if __name__ == "__main__":
    main()
