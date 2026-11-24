"""Convert prepared terrain NetCDF files to GeoTIFF for FastRefineInterp."""
from pathlib import Path

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_origin
from scipy.interpolate import RegularGridInterpolator

root = Path(__file__).resolve().parent
out_model = root / "lib" / "terrain" / "EC_12P5KM"
out_fine = root / "lib" / "terrain" / "DEM_1km"
out_model.mkdir(parents=True, exist_ok=True)
out_fine.mkdir(parents=True, exist_ok=True)


def write_geotiff(path, lon_1d, lat_1d, data_2d_south_north):
    """Write GeoTIFF north-up from south-north array on regular lon/lat grid."""
    lon = np.asarray(lon_1d, dtype=float)
    lat = np.asarray(lat_1d, dtype=float)
    data = np.asarray(data_2d_south_north, dtype=float)
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        data = data[:, ::-1]
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        data = data[::-1, :]
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])
    arr = np.asarray(data[::-1, :], dtype=np.float32)
    west = float(lon[0] - dlon / 2)
    north = float(lat[-1] + dlat / 2)
    transform = from_origin(west, north, dlon, dlat)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        compress="deflate",
    ) as dst:
        dst.write(arr, 1)
    print(
        "wrote",
        path,
        "shape",
        arr.shape,
        "lon",
        float(lon[0]),
        float(lon[-1]),
        "lat",
        float(lat[0]),
        float(lat[-1]),
    )


def main():
    ds2t = xr.open_dataset(root / "TMP_2M/2026/20260728/2026072800.000.nc")
    lon_t = ds2t["lon"].values.astype(float)
    lat_t = ds2t["lat"].values.astype(float)
    ds2t.close()

    ds_o = xr.open_dataset(root / "ec_source_orography.nc")
    lon_o = ds_o["lon"].values.astype(float)
    lat_o = ds_o["lat"].values.astype(float)
    oro = (
        ds_o["surface_altitude"]
        .isel(member=0, level=0, time=0, dtime=0)
        .values.astype(float)
    )
    ds_o.close()
    if lat_o[0] > lat_o[-1]:
        lat_o = lat_o[::-1]
        oro = oro[::-1, :]
    if lon_o[0] > lon_o[-1]:
        lon_o = lon_o[::-1]
        oro = oro[:, ::-1]
    interp = RegularGridInterpolator(
        (lat_o, lon_o), oro, bounds_error=False, fill_value=np.nan
    )
    Lon, Lat = np.meshgrid(lon_t, lat_t)
    oro_on_2t = interp((Lat, Lon))
    n_nan = int(np.isnan(oro_on_2t).sum())
    oro_on_2t = np.nan_to_num(oro_on_2t, nan=0.0)
    print("model oro remapped onto TMP_2M; nan_filled", n_nan, "of", oro_on_2t.size)
    write_geotiff(out_model / "Terrain_12P5km.tif", lon_t, lat_t, oro_on_2t)

    ds1 = xr.open_dataset(root / "HGT_M_1KM_CHINA.nc")
    lon1 = ds1["lon"].values.astype(float)
    lat1 = ds1["lat"].values.astype(float)
    h1 = (
        ds1["surface_altitude"]
        .isel(member=0, level=0, time=0, dtime=0)
        .values.astype(float)
    )
    ds1.close()
    write_geotiff(out_fine / "Terrain_1km.tif", lon1, lat1, h1)
    print("done")


if __name__ == "__main__":
    main()
