# -*- coding: utf-8 -*-
"""极坐标质控相关 I/O 辅助（非 CliBase 入口）。

命令行入口见 ``cli/radar_qc_cli.py``（``RadarQcCli`` / ``process``）。
本模块提供 ``save_meteva_grid_to_netcdf``（float32 + CF ``_FillValue``），
避免 ``meb.write_griddata_to_nc`` 的 int32 缩放把 NaN 写坏。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

# CF 惯例缺测；避免 meteva write_griddata_to_nc 的 int32 缩放把 NaN 写成约 -2147483.6
_CF_NETCDF_FILL = np.float32(9.969209968386869e36)


def _sanitize_grid_values_for_nc(values: np.ndarray) -> np.ndarray:
    """将 NaN/异常极值统一为 NetCDF 缺测填充值（float32）。"""
    arr = np.asarray(values, dtype=np.float32).copy()
    invalid = ~np.isfinite(arr)
    invalid |= np.abs(arr) >= np.float32(1e19)
    invalid |= arr <= np.float32(-1e6)
    invalid |= np.abs(arr + 2147483.648) < np.float32(1.0)
    arr[invalid] = _CF_NETCDF_FILL
    return arr


def save_meteva_grid_to_netcdf(
    grid_data: xr.DataArray,
    output_path=None,
    compression: bool = True,
    show: bool = False,
) -> Path:
    """保存 meteva 网格为 NetCDF（float32 + CF ``_FillValue``）。"""
    import meteva_base as meb

    if output_path is None:
        raise TypeError("save_meteva_grid_to_netcdf requires output_path")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = meb.checkout_griddata(grid_data, is_single=False)
    var_name = normalized.name or "data0"
    out = normalized.copy()
    out.values = _sanitize_grid_values_for_nc(out.values)
    if not out.attrs.get("units"):
        out.attrs["units"] = ""
    out.attrs.pop("_FillValue", None)
    out.attrs.pop("missing_value", None)

    ds = out.to_dataset(name=var_name)
    encoding: dict = {}
    for v in ds.data_vars:
        ds[v].attrs.pop("_FillValue", None)
        ds[v].attrs.pop("missing_value", None)
        enc = {
            "dtype": "float32",
            "_FillValue": _CF_NETCDF_FILL,
            "missing_value": _CF_NETCDF_FILL,
        }
        if compression:
            enc["zlib"] = True
            enc["complevel"] = 4
        encoding[v] = enc

    ds.to_netcdf(str(output_path), encoding=encoding)
    if show:
        print(f"saved {output_path}")
    return output_path


__all__ = [
    "save_meteva_grid_to_netcdf",
]
