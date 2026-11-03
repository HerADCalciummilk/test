# FY4B AGRI L1 Lat/Lon Channel Plugins

This is a NIMM-style Python plugin set for FY-4B AGRI L1 HDF channel parsing.

The code converts FY-4B AGRI HDF files to regular latitude/longitude NetCDF files, split by channel.

## Batch Output Layout

Batch output uses the requested naming rule:

```text
output_root/
  CH01/
    YYYYMMDD/
      YYYYMMDDHH.nc
  CH02/
    YYYYMMDD/
      YYYYMMDDHH.nc
  ...
  CH15/
    YYYYMMDD/
      YYYYMMDDHH.nc
```

Each channel file contains:

```text
channel_value(lat, lon)
lat
lon
```

## 命令行调用示例

在本包目录下执行 `python -m cli`。没写的参数先读 `resource/fy4.ini`，再没有则用预设。

```bash
python -m cli --module batch --input-root /mnt/data_229/SatelliteData/fy4b_l1 --output-root /mnt/data_229/SatelliteData/fy4b_channel_latlon --start-time 2023010406 --end-time 2023010423
python -m cli --module single --input-hdf D:/testdata/FY4/input.HDF --output-dir D:/testdata/FY4/channel_data/case_name
```

## Batch Plugin Usage

```python
from fy4_batch_latlon_channel_plugin import FY4BatchLatLonChannelPlugin

plugin = FY4BatchLatLonChannelPlugin(
    input_root="/mnt/data_229/SatelliteData/fy4b_l1",
    output_root="/mnt/data_229/SatelliteData/fy4b_channel_latlon",
    start_time="2023010406",
    end_time="2023010423",
    resolution=0.04,
    lat_min=-60,
    lat_max=60,
    lon_half_width=75,
    channels="1-15",
    resampling="bilinear",
    centers=("1050E", "1330E"),
    overwrite=False,
    recursive=False,
)

files = plugin.process()
```

`start_time` and `end_time` support:

```text
YYYYMMDD
YYYYMMDDHH
YYYYMMDDHHMM
YYYYMMDDHHMMSS
```

The batch plugin scans existing HDF files and skips missing dates/times automatically. It recognizes both `1050E` and `1330E` from the file name.

## Single File Plugin Usage

```python
from fy4_latlon_channel_plugin import FY4LatLonChannelPlugin

plugin = FY4LatLonChannelPlugin(
    resolution=0.04,
    lat_min=-60,
    lat_max=60,
    lon_half_width=75,
    channels="1-15",
    resampling="bilinear",
)

files = plugin.process(
    input_hdf=r"D:\testdata\FY4\input.HDF",
    output_dir=r"D:\testdata\FY4\channel_data\case_name",
)
```

## Method

1. Read `Data/NOMChannelXX` from the original HDF.
2. Calibrate DN values with `Calibration/CALChannelXX`.
3. Build a regular latitude/longitude target grid.
4. Map target grid cells back to the native FY-4 geostationary fixed grid.
5. Resample calibrated channel values with `bilinear` or `nearest`.
6. Write one NetCDF file per channel.

Regular latitude/longitude output is a resampled product. The original FY-4 grid is not a regular latitude/longitude grid.

## Code Layout

```text
fy4_batch_latlon_channel_plugin.py  # batch plugin entry
fy4_latlon_channel_plugin.py        # single-file plugin entry
run_fy4_batch_plugin.py             # server batch example
run_fy4_plugin.py                   # single-file example
fy4agri/
  metadata.py                       # channel metadata and HDF attribute helpers
  projection.py                     # FY-4 geostationary projection formulas
  reader.py                         # calibration and resampling helpers
```
