#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""region_dealias 模块 CLI 入口与读写辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr


_CLI_SCRIPTS = (
    "radar_wind_dealiasing/cli/region_dealias.py",
)

# netCDF 库对 float32 的默认填充值（NC_FILL_FLOAT），与 netCDF4.default_fillvals['f4'] 相同。
_CF_NETCDF_FILL = np.float32(9.969209968386869e36)


def _read_griddata(path: str, value_name: Optional[str] = None) -> xr.DataArray:
    """读取六维网格字段，并保留极坐标体扫辅助坐标。"""
    try:
        with xr.open_dataset(path) as dataset:
            if value_name is not None:
                if value_name not in dataset.data_vars:
                    raise ValueError(
                        f"Cannot read value_name={value_name!r} from {path}"
                    )
                data = dataset[value_name].load()
            else:
                required_dims = {
                    "member",
                    "level",
                    "time",
                    "dtime",
                    "lat",
                    "lon",
                }
                candidates = [
                    name
                    for name, variable in dataset.data_vars.items()
                    if required_dims.issubset(variable.dims)
                ]
                if len(candidates) != 1:
                    raise ValueError(
                        "input file must contain exactly one six-dimensional "
                        "field when value_name is not specified"
                    )
                data = dataset[candidates[0]].load()
        return data.transpose("member", "level", "time", "dtime", "lat", "lon")
    except Exception as exc:
        raise RuntimeError(f"Failed to read input file: {path}") from exc


def _read_npy_array(path: str) -> np.ndarray:
    """从 ``.npy`` 文件读取一个 numpy 数组。"""
    file_path = Path(path)
    if file_path.suffix.lower() != ".npy":
        raise ValueError("input file must be a .npy file")
    return np.load(file_path)


def _sanitize_grid_values_for_nc(values: np.ndarray) -> np.ndarray:
    """将 NaN/异常极值统一为 NetCDF 缺测填充值（float32）。

    与 ``qpe.cli.cinrad_meb`` 策略一致：避免 ``meteva_base.write_griddata_to_nc``
    的 int32 缩放把 NaN 写成约 ``-2147483.6``，并把常用 ``-9999`` 哨兵一并归入缺测。
    """
    arr = np.asarray(values, dtype=np.float32).copy()
    invalid = ~np.isfinite(arr)
    invalid |= np.abs(arr) >= np.float32(1e19)
    invalid |= arr <= np.float32(-1e6)
    invalid |= np.abs(arr + 2147483.648) < np.float32(1.0)
    arr[invalid] = _CF_NETCDF_FILL
    return arr


def _write_griddata_to_nc(
    data: xr.DataArray,
    output_path: str | Path,
    *,
    compression: bool = True,
) -> Path:
    """保存 region_dealias 网格结果为 NetCDF（float32 + CF 缺测值）。

    对齐 ``qpe.cli.cinrad_meb.save_meteva_grid_to_netcdf`` 的核心落盘策略。
    本模块 attrs 以 str/数值/ndarray 为主，无需 echo_class 那套嵌套 attrs 序列化。
    """
    if not isinstance(data, xr.DataArray):
        raise TypeError("_write_griddata_to_nc only supports xarray.DataArray")

    path_obj = Path(output_path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    var_name = data.name if data.name else "data"
    out = data.copy()
    out.values = _sanitize_grid_values_for_nc(out.values)
    out.attrs.pop("_FillValue", None)
    out.attrs.pop("missing_value", None)

    dataset = out.to_dataset(name=var_name)
    encoding: dict = {}
    for data_var in dataset.data_vars:
        dataset[data_var].attrs.pop("_FillValue", None)
        dataset[data_var].attrs.pop("missing_value", None)
        enc = {
            "dtype": "float32",
            "_FillValue": _CF_NETCDF_FILL,
            "missing_value": _CF_NETCDF_FILL,
        }
        if compression:
            enc["zlib"] = True
            enc["complevel"] = 4
        encoding[data_var] = enc

    try:
        dataset.to_netcdf(str(path_obj), mode="w", encoding=encoding)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot write output file: {path_obj}. "
            "The file may be open in another process (for example, Jupyter). "
            "Please close dataset handles or use a different output path."
        ) from exc

    return path_obj


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "region_dealias CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
