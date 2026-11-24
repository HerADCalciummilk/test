"""Crop multi-level TMP/HGT to the surface-field domain (60–140E, 0–60N)."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / "_backup_before_crop"
LON_MIN, LON_MAX = 60.0, 140.0
LAT_MIN, LAT_MAX = 0.0, 60.0


def crop_ds(ds: xr.Dataset) -> xr.Dataset:
    lon = ds["lon"]
    lat = ds["lat"]
    # inclusive bounds on regular grids
    return ds.sel(
        lon=lon[(lon >= LON_MIN - 1e-8) & (lon <= LON_MAX + 1e-8)],
        lat=lat[(lat >= LAT_MIN - 1e-8) & (lat <= LAT_MAX + 1e-8)],
    )


def main() -> None:
    BACKUP.mkdir(exist_ok=True)
    targets = []
    for elem in ("TMP", "HGT"):
        targets.extend(sorted((ROOT / elem).rglob("*.nc")))

    print("files_to_crop", len(targets))
    for src in targets:
        rel = src.relative_to(ROOT)
        bak = BACKUP / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        if not bak.exists():
            shutil.copy2(src, bak)

        ds = xr.open_dataset(src)
        before = dict(ds.sizes)
        out = crop_ds(ds)
        after = dict(out.sizes)
        # write atomically
        tmp = src.with_suffix(".nc.tmp")
        # keep encoding simple
        out.load()
        ds.close()
        out.to_netcdf(tmp)
        out.close()
        tmp.replace(src)
        print(rel, before, "->", after)

    # verify surface/PRES already match
    for rel in (
        "TMP_2M/2026/20260728/2026072800.006.nc",
        "PRES/2026/20260728/2026072800.006.nc",
    ):
        ds = xr.open_dataset(ROOT / rel)
        lon = ds["lon"].values
        lat = ds["lat"].values
        print(
            rel,
            "lon",
            float(lon.min()),
            float(lon.max()),
            "lat",
            float(lat.min()),
            float(lat.max()),
            "shape",
            dict(ds.sizes),
        )
        ds.close()

    print("common_domain", LON_MIN, LON_MAX, LAT_MIN, LAT_MAX)
    print("backup", BACKUP)


if __name__ == "__main__":
    main()
