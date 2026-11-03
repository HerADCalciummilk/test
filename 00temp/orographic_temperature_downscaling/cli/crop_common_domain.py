# -*- coding: utf-8 -*-
"""将 EC / 源地形 / 掩码 / 1km 目标地形裁到公共域（避开边界缺测）。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import meteva_base as meb

# 交集内再内缩，避开 HGT 边界 fill 与源地形西侧无效区
# HGT 有效约 lon 70.04–140、lat 15.04–59.99；实况 lon≥70；EC 0.1° 网格对齐
LAT_MIN, LAT_MAX = 16.0, 59.0
LON_MIN, LON_MAX = 71.0, 139.0
FILL_ABS = 1.0e5


def _clean(v: np.ndarray) -> np.ndarray:
    out = np.asarray(v, dtype=np.float32).copy()
    out = np.where(np.abs(out) > FILL_ABS, np.nan, out)
    return out


def _crop_grd(grd, lat_min, lat_max, lon_min, lon_max):
    lat = grd.lat.values
    lon = grd.lon.values
    lat_sel = (lat >= lat_min) & (lat <= lat_max)
    lon_sel = (lon >= lon_min) & (lon <= lon_max)
    if not lat_sel.any() or not lon_sel.any():
        raise RuntimeError("裁剪后无格点，请检查范围")
    out = grd.isel(lat=lat_sel, lon=lon_sel)
    out = out.copy(data=_clean(out.values))
    return out


def _write(grd, path: Path, name: str | None = None, units: str | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if name:
        grd = grd.copy()
        grd.name = name
    if units is not None:
        grd = grd.copy()
        grd.attrs["units"] = units
    meb.write_griddata_to_nc(grd, str(path), creat_dir=True)


def main() -> None:
    pkg = Path(__file__).resolve().parents[1]
    data = pkg / "resource" / "data"
    out_root = data / "common_domain"
    ancil_in = data / "ancil"
    ancil_out = out_root / "ancil"
    ec_in = data / "ec_tmp2m"
    ec_out = out_root / "ec_tmp2m"

    meta = {
        "lat_min": LAT_MIN,
        "lat_max": LAT_MAX,
        "lon_min": LON_MIN,
        "lon_max": LON_MAX,
        "note": "intersection of EC/obs/HGT with margin; fill |v|>1e5 -> nan",
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "domain.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ancil
    for src_name, dst_name, vname, units in [
        ("ec_source_orography.nc", "ec_source_orography.nc", "surface_altitude", "m"),
        ("ec_land_sea_mask.nc", "ec_land_sea_mask.nc", "land_binary_mask", "1"),
        ("HGT_M_1KM_CHINA.nc", "HGT_M_1KM_CHINA.nc", "surface_altitude", "m"),
    ]:
        grd = meb.read_griddata_from_nc(str(ancil_in / src_name))
        cropped = _crop_grd(grd, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)
        # mask keep 0/1
        if "mask" in src_name:
            vals = np.asarray(cropped.values, dtype=np.float32)
            vals = np.where(np.isnan(vals), 0.0, vals)
            vals = (vals >= 0.5).astype(np.float32)
            cropped = cropped.copy(data=vals)
        _write(cropped, ancil_out / dst_name, name=vname, units=units)
        v = np.asarray(cropped.values)
        print(
            dst_name,
            cropped.shape,
            "lat",
            float(cropped.lat.min()),
            float(cropped.lat.max()),
            "lon",
            float(cropped.lon.min()),
            float(cropped.lon.max()),
            "finite%",
            float(np.isfinite(v).mean()),
            "nan%",
            float(np.isnan(v).mean()),
        )

    # EC temperatures
    n = 0
    for nc in sorted(ec_in.rglob("*.nc")):
        rel = nc.relative_to(ec_in)
        grd = meb.read_griddata_from_nc(str(nc))
        cropped = _crop_grd(grd, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX)
        _write(cropped, ec_out / rel)
        n += 1
    print(f"cropped EC files: {n}")

    # HRCLDAS: 无 cfgrib 时跳过，仅记录路径约定
    obs_in = data / "hrcldas_tair"
    obs_out = out_root / "hrcldas_tair"
    obs_out.mkdir(parents=True, exist_ok=True)
    readme = obs_out / "README.txt"
    readme.write_text(
        "HRCLDAS GRIB2 请在读入后按 domain.json 裁剪到 "
        f"lat[{LAT_MIN},{LAT_MAX}] lon[{LON_MIN},{LON_MAX}]；"
        "本脚本未改写 GRIB（环境可能无 cfgrib）。\n"
        f"原始目录: {obs_in}\n",
        encoding="utf-8",
    )
    print("wrote", out_root)
    print("domain", meta)


if __name__ == "__main__":
    main()
