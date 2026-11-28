"""Export per-element grid products using the model input naming convention."""

from datetime import datetime, timedelta
from pathlib import Path
import os
import tempfile

import h5py
import numpy as np


UNITS = {"2t": "degC", "2rh": "%", "10u": "m s-1", "10v": "m s-1",
         "10ws": "m s-1", "10gust": "m s-1", "sp": "Pa",
         "mx2t3": "degC", "mn2t3": "degC", "tcc": "%"}
ALIASES = {"10gust": "10fg3"}


def product_path(root, element_dir, reference_time, hour, level=None):
    directory = Path(element_dir)
    if directory.is_absolute() or len(directory.parts) != 1 or element_dir in (".", ".."):
        raise ValueError(f"Element directory must be a single directory name: {element_dir}")
    target = Path(root) / directory
    if level is not None:
        target /= str(level)
    return target / reference_time.strftime("%Y/%Y%m%d") / (
        reference_time.strftime("%Y%m%d%H") + f".{int(hour):03d}.nc"
    )


def export_grid_file(h5_path, output_root, begin_bjt, hour, element_dirs,
                     file_timezone="UTC", update=False, fill_value=-32766.0):
    from netCDF4 import Dataset, date2num

    reference_time = datetime.strptime(begin_bjt, "%Y%m%d%H")
    if file_timezone.upper() == "UTC":
        reference_time -= timedelta(hours=8)
    elif file_timezone.upper() != "BJT":
        raise ValueError("NetCDF file_timezone must be UTC or BJT")
    paths = []
    with h5py.File(h5_path, "r") as source:
        west, east, south, north, dx, dy = source["lon_lat"][:]
        lon = west + np.arange(round((east - west) / dx) + 1) * dx
        lat = south + np.arange(round((north - south) / dy) + 1) * dy
        for key in source:
            if key == "lon_lat" or key.startswith("gamma_"):
                continue
            mapping_key = ALIASES.get(key, key)
            if mapping_key not in element_dirs:
                raise ValueError(f"Missing [ElementDirGround] mapping for output {key}")
            target = product_path(output_root, element_dirs[mapping_key], reference_time, hour)
            paths.append(str(target))
            if target.exists() and not update:
                continue
            values = source[key][:]
            if values.shape != (len(lat), len(lon)):
                raise ValueError(f"Unexpected grid shape for {key}: {values.shape}")
            valid = np.isfinite(values) & (values != fill_value)
            # The interpolation core uses hPa internally; EC input pressure uses Pa.
            if key == "sp":
                values = np.where(valid, values * 100.0, fill_value)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".nc.tmp")
            os.close(fd)
            try:
                with Dataset(temporary, "w", format="NETCDF4") as ds:
                    ds.element = key
                    ds.file_timezone = file_timezone.upper()
                    ds.source_file = Path(h5_path).name
                    ds.forecast_reference_time = reference_time.isoformat()
                    ds.valid_time = (reference_time + timedelta(hours=int(hour))).isoformat()
                    for name, size in (("member", 1), ("level", 1), ("time", 1),
                                       ("dtime", 1), ("lat", len(lat)), ("lon", len(lon))):
                        ds.createDimension(name, size)
                    for name, data in (("member", [0]), ("level", [0]), ("dtime", [hour])):
                        var = ds.createVariable(name, "i4", (name,))
                        var[:] = data
                    ds.variables["dtime"].units = "hours"
                    ds.variables["level"].long_name = "surface field; not a pressure level"
                    time = ds.createVariable("time", "f8", ("time",))
                    time.units = "hours since 1970-01-01 00:00:00"
                    time.calendar = "standard"
                    time[:] = [date2num(reference_time, time.units, time.calendar)]
                    for name, data, units in (("lat", lat, "degrees_north"), ("lon", lon, "degrees_east")):
                        var = ds.createVariable(name, "f8", (name,))
                        var.units = units
                        var[:] = data
                    var = ds.createVariable("data0", "f8", (
                        "member", "level", "time", "dtime", "lat", "lon"
                    ), fill_value=fill_value, zlib=True, complevel=4)
                    var.long_name = key
                    if key in UNITS:
                        var.units = UNITS[key]
                    var[0, 0, 0, 0, :, :] = np.where(valid, values, fill_value)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
    return paths
