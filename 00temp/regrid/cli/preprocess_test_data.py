#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方 Iris 样例预处理为六维 meb，写入 ``test_data/cli_input/``。

供 CLI / pytest /验证 Notebook 共用。

用法（仓库根目录）::

    python regrid/cli/preprocess_test_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import xarray as xr
import meteva_base as meb

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = PACKAGE_ROOT / "test_data"
CLI_INPUT_DIR = DATA_DIR / "cli_input"

SPATIAL_RENAME = {
    "latitude": "lat",
    "longitude": "lon",
    "projection_y_coordinate": "lat",
    "projection_x_coordinate": "lon",
}

# (写出文件名, 官方源路径, 可选变量名)
CLI_INPUT_SPECS = [
    ("global_cutout.nc", DATA_DIR / "global_cutout.nc", "air_temperature"),
    ("ukvx_grid.nc", DATA_DIR / "ukvx_grid.nc", "air_temperature"),
    ("glm_landmask.nc", DATA_DIR / "landmask" / "glm_landmask.nc", "land_binary_mask"),
    ("ukvx_landmask.nc", DATA_DIR / "landmask" / "ukvx_landmask.nc", "land_binary_mask"),
    ("engl_landmask.nc", DATA_DIR / "landmask" / "engl_landmask.nc", "land_binary_mask"),
    (
        "global_cutout_multi_realization.nc",
        DATA_DIR / "landmask" / "global_cutout_multi_realization.nc",
        "air_temperature",
    ),
]


def official_to_meb6d(nc_path: Path, var_name: str | None = None) -> xr.DataArray:
    """将官方 Improver 样例 NetCDF 转为本模块使用的六维 meb ``DataArray``。

    转换约定（供 ``RegridLandSea`` / CLI / pytest 读取）：

    - 空间维：``latitude``/``longitude`` 或 ``projection_y/x_coordinate``
      → ``lat``/``lon``；投影场保留米制坐标 attrs，并把 ``grid_mapping``
      变量属性写入 ``attrs["grid_mapping_attrs"]``（JSON 字符串）。
    - 集合维：``realization`` → ``member``；无该维时 ``member`` 取 ``[0]``。
    - 其余非空间维（如 ``time``、阈值等）取第 0 个切片并丢弃，使输出固定为
      ``(member, level, time, dtime, lat, lon)``；``level``/``time``/``dtime``
      使用占位坐标（本预处理不保留原时间/阈值语义）。
    - 仅支持空间二维场，或带 ``member`` 的三维场；其它形状会报错。

    参数
    ----------
    nc_path :
        官方样例 NetCDF 路径。
    var_name :
        主变量名。为 ``None`` 时自动选取第一个非网格映射、非 ``*_bnds`` 的
        data variable。

    返回
    -------
    xr.DataArray
        六维 meb 场；投影输入在 attrs 中带 ``grid_mapping_attrs``。
    """
    ds = xr.open_dataset(nc_path, decode_timedelta=False)
    try:
        if var_name is None:
            skip = {"latitude_longitude", "lambert_azimuthal_equal_area"}
            candidates = [
                v
                for v in ds.data_vars
                if v not in skip and not str(v).endswith("_bnds")
            ]
            if not candidates:
                raise ValueError(f"未找到主变量: {nc_path}")
            var_name = candidates[0]
        da = ds[var_name].load()
        gm = da.attrs.get("grid_mapping")
        if isinstance(gm, str) and gm in ds.variables:
            mapping = {}
            for key, value in dict(ds[gm].attrs).items():
                if isinstance(value, np.ndarray):
                    mapping[key] = value.tolist()
                elif isinstance(value, np.generic):
                    mapping[key] = value.item()
                else:
                    mapping[key] = value
            da.attrs["grid_mapping_attrs"] = json.dumps(mapping, ensure_ascii=False)
    finally:
        ds.close()

    arr = da
    rename = {
        k: v for k, v in SPATIAL_RENAME.items() if k in arr.dims or k in arr.coords
    }
    if rename:
        arr = arr.rename(rename)
    if "realization" in arr.dims:
        arr = arr.rename({"realization": "member"})
    for dim in list(arr.dims):
        if dim not in {"lat", "lon", "member"}:
            arr = arr.isel({dim: 0}, drop=True)

    lat_coord = arr.coords["lat"]
    lon_coord = arr.coords["lon"]
    if "projection_y_coordinate" in da.dims or "projection_x_coordinate" in da.dims:
        lat_attrs = dict(lat_coord.attrs)
        lon_attrs = dict(lon_coord.attrs)
        lat_attrs.setdefault("units", "m")
        lon_attrs.setdefault("units", "m")
        lat_attrs.setdefault("standard_name", "projection_y_coordinate")
        lon_attrs.setdefault("standard_name", "projection_x_coordinate")
        lat_coord = xr.DataArray(lat_coord.values, dims=("lat",), attrs=lat_attrs)
        lon_coord = xr.DataArray(lon_coord.values, dims=("lon",), attrs=lon_attrs)

    values = np.asarray(arr.values, dtype=np.float32)
    if values.ndim == 2:
        values = values[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
        member_coord = np.array([0], dtype=np.int32)
    elif values.ndim == 3 and "member" in arr.dims:
        values = values[:, np.newaxis, np.newaxis, np.newaxis, :, :]
        member_coord = np.asarray(arr.coords["member"].values)
    else:
        raise ValueError(f"暂不支持的数组形状: {values.shape}, dims={arr.dims}")

    attrs = {
        "units": str(arr.attrs.get("units", "1")),
    }
    gma = arr.attrs.get("grid_mapping_attrs")
    if isinstance(gma, str) and gma.strip():
        parsed = json.loads(gma)
        gm_name = str(parsed.get("grid_mapping_name", "")).lower()
        if gm_name and gm_name != "latitude_longitude":
            attrs["grid_mapping_attrs"] = gma

    da = xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member_coord,
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array(
                [np.datetime64("1970-01-01T00:00:00")], dtype="datetime64[ns]"
            ),
            "dtime": np.array([0], dtype=np.int32),
            "lat": lat_coord,
            "lon": lon_coord,
        },
        name=arr.name,
        attrs=attrs,
    )
    # 补齐 meb 标准默认属性（已有 units 等保留）
    meb.set_griddata_attrs(
        da,
        units=da.attrs.get("units"),
        model_var=da.attrs.get("model_var"),
        dtime_units=da.attrs.get("dtime_units"),
        level_type=da.attrs.get("level_type"),
        time_type=da.attrs.get("time_type"),
        time_bounds=da.attrs.get("time_bounds"),
        is_default=True,
    )
    return da


def save_meb6d_to_nc(data: xr.DataArray, dst_path: Path) -> None:
    """写出六维 meb NetCDF（覆盖已存在文件）。"""
    path = Path(dst_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = data.copy(deep=True)
    normalized.attrs = {
        k: ("" if v is None else v) for k, v in dict(normalized.attrs).items()
    }
    var_name = normalized.name if normalized.name else "data"
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    normalized.to_dataset(name=var_name).to_netcdf(tmp)
    try:
        tmp.replace(path)
    except PermissionError as err:
        raise PermissionError(
            f"无法覆盖 {path}（可能被 Jupyter 或其他进程占用）。"
            f"临时文件已写至 {tmp}，请关闭占用后重试。"
        ) from err
    print(f"写出: {path}")


def main() -> None:
    missing = [str(src_path) for _, src_path, _ in CLI_INPUT_SPECS if not src_path.exists()]
    if missing:
        print(
            "官方样例缺失，无法预处理 cli_input：\n  - "
            + "\n  - ".join(missing)
            + "\n请补齐 test_data 后再运行。"
        )
        return
    CLI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    for out_name, src_path, var_name in CLI_INPUT_SPECS:
        meb6d = official_to_meb6d(src_path, var_name)
        save_meb6d_to_nc(meb6d, CLI_INPUT_DIR / out_name)
    print(f"cli_input 预处理完成: {CLI_INPUT_DIR}")


if __name__ == "__main__":
    main()
