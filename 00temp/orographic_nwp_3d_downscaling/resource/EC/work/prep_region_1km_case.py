#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare SW-China regional 1km case (显著地形区):
  lon 90–108E, lat 25–38N  (~1801×1301)
- crop/resample DEM → Terrain_1km.tif + Zoning_1km.tif
- write HRCLDAS t2m onto same grid as NC for obs_path
- update Obs_Info Grid_1km bounds
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
import xarray as xr

EC = Path(__file__).resolve().parents[1]
DEM_DIR = EC / "lib" / "terrain" / "DEM_1km"
DEM_FULL = DEM_DIR / "Terrain_1km_fullChina.tif"
DEM_SRC = DEM_DIR / "Terrain_1km.tif"
ZONING = DEM_DIR / "Zoning_1km.tif"

LON0, LON1 = 90.0, 108.0
LAT0, LAT1 = 25.0, 38.0
RES = 0.01

OBS_GRB = next((EC.parent / "hrcldas_tair" / "2026" / "20260728").glob("*.GRB2"))
# ObsPathInfo: basepath/EC + Grid_1km + Hourly + TMP_2M (ElementDirGround 2t)
OBS_NC = (
    EC
    / "Grid_1km"
    / "Hourly"
    / "TMP_2M"
    / "2026"
    / "20260728"
    / "BJT_2026072814.000.nc"
)


def main() -> None:
    lon = np.round(np.arange(LON0, LON1 + RES * 0.5, RES), 5)
    lat = np.round(np.arange(LAT0, LAT1 + RES * 0.5, RES), 5)
    nlon, nlat = lon.size, lat.size
    print(f"target grid lon[{LON0},{LON1}] lat[{LAT0},{LAT1}] res={RES} → {nlat}×{nlon}={nlat*nlon}")

    # backup full DEM once
    if DEM_SRC.exists() and not DEM_FULL.exists():
        DEM_FULL.write_bytes(DEM_SRC.read_bytes())
        print("backed up full DEM →", DEM_FULL.name)

    src_path = DEM_FULL if DEM_FULL.exists() else DEM_SRC
    with rasterio.open(src_path) as src:
        # sample DEM onto target grid centers
        # rasterio xy: row 0 is north if north-up; our lat ascending south→north for algorithm
        xs, ys = np.meshgrid(lon, lat)
        samples = list(src.sample(zip(xs.ravel(), ys.ravel())))
        dem = np.array([s[0] for s in samples], dtype=np.float32).reshape(nlat, nlon)
        nodata = src.nodata
        if nodata is not None:
            dem = np.where(dem == nodata, np.nan, dem)
        # also treat extreme fill as nan
        dem = np.where(np.abs(dem) > 9000, np.nan, dem)

    # write GeoTIFF north-up (lat descending in rows) for GIS convention;
    # algorithm dRead_Terrain flips — check dRead_Terrain
    transform = from_origin(LON0 - RES / 2, LAT1 + RES / 2, RES, RES)
    dem_north_up = dem[::-1, :]  # row0 = north
    profile = {
        "driver": "GTiff",
        "height": nlat,
        "width": nlon,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
        "compress": "lzw",
        "nodata": -32766.0,
    }
    dem_out = np.where(np.isfinite(dem_north_up), dem_north_up, -32766.0).astype(np.float32)
    with rasterio.open(DEM_SRC, "w", **profile) as dst:
        dst.write(dem_out, 1)
    print("wrote", DEM_SRC, dem_out.shape)

    zoning = np.where(dem_out > -1000, 1, 0).astype(np.int16)
    profile_z = dict(profile)
    profile_z["dtype"] = "int16"
    profile_z["nodata"] = 0
    with rasterio.open(ZONING, "w", **profile_z) as dst:
        dst.write(zoning, 1)
    print("wrote", ZONING, "land_frac", float(zoning.mean()))

    # HRCLDAS → same grid, Celsius, data0
    ds = xr.open_dataset(OBS_GRB, engine="cfgrib")
    t = ds["t2m"]
    if float(t.mean()) > 200:
        t = t - 273.15
    # cfgrib lat often ascending; interp to target
    t2 = t.interp(longitude=lon, latitude=lat, method="linear")
    arr = np.asarray(t2.values, dtype=np.float32)
    ds.close()
    # ensure (lat, lon) with lat ascending
    out = xr.Dataset(
        {"data0": (("lat", "lon"), arr)},
        coords={"lat": lat.astype(np.float32), "lon": lon.astype(np.float32)},
    )
    out["data0"].attrs["units"] = "C"
    OBS_NC.parent.mkdir(parents=True, exist_ok=True)
    out.to_netcdf(OBS_NC)
    print("wrote", OBS_NC, arr.shape, "mean", float(np.nanmean(arr)))

    # patch Obs_Info.ini Grid_1km
    obs_ini = EC / "Parameter" / "Obs_Info.ini"
    text = obs_ini.read_text(encoding="utf-8")
    # replace Grid_1km block simply
    import re

    block = f"""[Grid_1km]
path = {str(EC / 'obs' / 'grid_1km').replace(chr(92), '/')}
lat_north = {LAT1}
lat_south = {LAT0}
lon_west = {LON0}
lon_east = {LON1}
reso_lat = {RES}
reso_lon = {RES}
"""
    if "[Grid_1km]" in text:
        text = re.sub(r"\[Grid_1km\][\s\S]*?(?=\n\[|\Z)", block.strip() + "\n\n", text)
    else:
        text = text.rstrip() + "\n\n" + block
    obs_ini.write_text(text, encoding="utf-8")
    print("updated", obs_ini)

    # ObsPathInfo must find Grid_1km under basepath
    mop = EC / "Parameter" / "Mdl_Obs_Path_Info.ini"
    mop_txt = mop.read_text(encoding="utf-8")
    mop_txt = mop_txt.replace(
        "Grid_1km = Grid_1km",
        "Grid_1km = Grid_1km",
    )
    # ensure Obs timezone BJT for BJT_ file names
    mop_txt = mop_txt.replace(
        """[ObsPathInfo]
basepath = D:/workspace/test/00temp/orographic_nwp_3d_downscaling/resource/EC
Grid_5km = Grid_5km
Grid_1km = Grid_1km
timezone = UTC
file_timezone = UTC""",
        """[ObsPathInfo]
basepath = D:/workspace/test/00temp/orographic_nwp_3d_downscaling/resource/EC
Grid_5km = Grid_5km
Grid_1km = Grid_1km
timezone = BJT
file_timezone = BJT""",
    )
    mop.write_text(mop_txt, encoding="utf-8")
    print("updated ObsPathInfo timezone → BJT")
    print("DONE region case prep")


if __name__ == "__main__":
    main()
