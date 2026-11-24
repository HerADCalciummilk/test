#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replicate InstantInfo.validate / dvalidate_1PQ_site metrics for 2t:
  - bi = model-field bilinear to stations vs obs
  - lr = refined product vs obs
  - MAE + hit rate (AE <= threshold)
Also reports bias/rmse for documentation.
"""

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
OBS_GRB = next((RES / "hrcldas_tair" / "2026" / "20260728").glob("*.GRB2"))
# algorithm site-obs layout (Obs_Info.ini Site.path)
OBS_SITE_H5 = (
    EC
    / "obs"
    / "site"
    / "2026"
    / "Temperature"
    / "H00_Inst"
    / "20260728"
    / "202607281400.h5"
)
THRESHOLD_2T = 2.0  # Fast_refine_interp_site.ini [threshold] 2t


def read_stations(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    rows = []
    for line in lines[1:]:
        p = line.split()
        rows.append(
            {"id": p[0], "name": p[1], "lon": float(p[2]), "lat": float(p[3]), "alt": float(p[4])}
        )
    return pd.DataFrame(rows)


def sample_field(lon1d, lat1d, data2d, lons, lats) -> np.ndarray:
    lat = lat1d.astype(float)
    lon = lon1d.astype(float)
    data = np.asarray(data2d, dtype=float)
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        data = data[::-1, :]
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        data = data[:, ::-1]
    interp = RegularGridInterpolator((lat, lon), data, bounds_error=False, fill_value=np.nan)
    return interp(np.column_stack([lats, lons]))


def main() -> None:
    df = read_stations(STATION)
    lons, lats = df["lon"].values, df["lat"].values

    # --- obs from HRCLDAS (K→℃), write algorithm site-obs h5 ---
    ds_o = xr.open_dataset(OBS_GRB, engine="cfgrib")
    obs = sample_field(
        ds_o["longitude"].values,
        ds_o["latitude"].values,
        ds_o["t2m"].values,
        lons,
        lats,
    )
    if np.nanmean(obs) > 200:
        obs = obs - 273.15
    ds_o.close()
    obs = np.round(obs, 1)  # dyPQ_round 2t=1

    OBS_SITE_H5.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(OBS_SITE_H5, "w") as f:
        for sid, val in zip(df["id"].astype(str), obs):
            f.create_dataset(sid, data=np.float32(val))
    print("wrote site obs h5:", OBS_SITE_H5)

    # --- before: bilinear from model TMP_2M (same as validate bi) ---
    ds_m = xr.open_dataset(TMP2M)
    mdl = np.asarray(ds_m["data0"].values, dtype=float).squeeze()
    if np.nanmean(mdl) > 200:
        mdl = mdl - 273.15
    bi = sample_field(ds_m["lon"].values, ds_m["lat"].values, mdl, lons, lats)
    ds_m.close()

    # --- after: refined site product (validate lr) ---
    with h5py.File(H5, "r") as f:
        sites = [x.decode() if isinstance(x, bytes) else str(x) for x in f["site"][:]]
        t_lr = np.asarray(f["2t"][:], dtype=float)
    order = [sites.index(s) for s in df["id"].astype(str)]
    lr = t_lr[order]

    # QC like algorithm
    qc = (obs >= -60) & (obs <= 60)
    bi = np.where(qc, bi, np.nan)
    lr = np.where(qc, lr, np.nan)
    obs_q = np.where(qc, obs, np.nan)

    diff_bi = bi - obs_q
    diff_lr = lr - obs_q
    ae_bi = np.abs(diff_bi)
    ae_lr = np.abs(diff_lr)

    mae_bi = float(np.round(np.nanmean(ae_bi), 3))
    mae_lr = float(np.round(np.nanmean(ae_lr), 3))
    hit_bi = float(
        np.round(
            (ae_bi <= THRESHOLD_2T).sum() / np.count_nonzero(~np.isnan(ae_bi)),
            3,
        )
    )
    hit_lr = float(
        np.round(
            (ae_lr <= THRESHOLD_2T).sum() / np.count_nonzero(~np.isnan(ae_lr)),
            3,
        )
    )

    # also bias/rmse (for docs; not printed by validate but useful)
    def br(pred, o):
        d = pred - o
        m = np.isfinite(d)
        return float(np.mean(d[m])), float(np.sqrt(np.mean(d[m] ** 2)))

    bias_bi, rmse_bi = br(bi, obs_q)
    bias_lr, rmse_lr = br(lr, obs_q)

    print("\n=== InstantInfo.validate logic (dvalidate_1PQ_site), 2t, threshold=2.0 ===")
    print(f"obs time BJT: 2026072814  n={int(np.count_nonzero(~np.isnan(obs_q)))}")
    print(f"2t-6h-Site-(lr,bi) MAE: {mae_lr:.3f} {mae_bi:.3f} | hit: {hit_lr:.3f} {hit_bi:.3f}")
    print(f"  (lr=refined, bi=bilinear; hit = fraction with |err|<={THRESHOLD_2T})")
    print("\n=== bias/rmse (same pairs, for ShowDoc-style table) ===")
    print(f"bi  bias={bias_bi:+.3f} rmse={rmse_bi:.3f}")
    print(f"lr  bias={bias_lr:+.3f} rmse={rmse_lr:.3f}")
    print(f"delta_rmse(lr-bi)={rmse_lr - rmse_bi:+.3f}")

    out = Path(__file__).resolve().parent / "method_validate_2t.csv"
    pd.DataFrame(
        {
            "id": df["id"],
            "name": df["name"],
            "alt": df["alt"],
            "obs": obs_q,
            "bi": bi,
            "lr": lr,
            "ae_bi": ae_bi,
            "ae_lr": ae_lr,
            "hit_bi": ae_bi <= THRESHOLD_2T,
            "hit_lr": ae_lr <= THRESHOLD_2T,
        }
    ).to_csv(out, index=False, float_format="%.3f")
    print("wrote", out)


if __name__ == "__main__":
    main()
