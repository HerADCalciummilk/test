# -*- coding: utf-8 -*-
"""
输出辅助工具：综合电码网格保存与统计打印
"""
import os
import logging

import numpy as np

from ..encoder import decode

logger = logging.getLogger(__name__)


def save_nc(filepath: str, result: np.ndarray,
            lat: np.ndarray, lon: np.ndarray,
            init_time: str, seg_idx: int):
    """
    将5位综合电码网格保存为 meteva 标准 6D DataArray 格式的 NetCDF4 文件
    维度顺序：[member, level, time, dtime, lat, lon]
    保存后可直接用 meteva.base.read_griddata_from_nc 读取
    """
    import xarray as xr
    import pandas as pd

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    ttt = seg_idx * 12  # 时段结束预报时效

    init_dt = pd.Timestamp(
        year=int(init_time[:4]),
        month=int(init_time[4:6]),
        day=int(init_time[6:8]),
        hour=int(init_time[8:10])
    )

    data_6d = result.astype(np.float32)[np.newaxis, np.newaxis,
                                         np.newaxis, np.newaxis, :, :]

    coords = {
        "member":  np.array(["data0"], dtype="<U5"),
        "level":   np.array([0.0], dtype=np.float32),
        "time":    [init_dt],
        "dtime":   np.array([ttt], dtype=np.int32),
        "lat":     lat.astype(np.float32),
        "lon":     lon.astype(np.float32),
    }
    dims = ["member", "level", "time", "dtime", "lat", "lon"]

    da = xr.DataArray(data_6d, coords=coords, dims=dims,
                      name="phenom_code")

    da.attrs["standard_name"] = "phenom_code"
    da.attrs["units"]         = "1"
    da.attrs["grid_mapping"]  = "latitude_longitude"
    da.attrs["model_var"]     = ""
    da.attrs["dtime_units"]   = "hour"
    da.attrs["level_type"]    = "surface"
    da.attrs["time_type"]     = "UT"
    da.attrs["time_bounds"]   = [(seg_idx - 1) * 12, seg_idx * 12]

    ds = da.to_dataset()
    ds.to_netcdf(filepath, format="NETCDF4", engine="netcdf4")

    logger.info(f"    已保存(meteva 6D格式) → {filepath}")


def print_stats(result: np.ndarray):
    """打印电码网格的天气现象分布统计"""
    unique, counts = np.unique(result, return_counts=True)
    total = result.size
    print(f"\n{'电码':>7}  {'表述':<14}  {'格点数':>8}  {'占比':>6}")
    print("-" * 45)
    for code_int, cnt in sorted(zip(unique, counts),
                                key=lambda x: -x[1])[:20]:
        info = decode(int(code_int))
        pct  = cnt / total * 100
        print(f"  {code_int:05d}  {info['预报表述']:<14}  {cnt:>8,}  {pct:5.1f}%")
