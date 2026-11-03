#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方投影样例预处理为六维 meb，供两条验证路径共用。

写出目录（均在 ``test_data/wind_calculations_data/`` 下）::

    cli_input/          方案一：投影维重命名（数值仍为米制）
    cli_input/latlon/   方案二：投影 → 规则经纬重网格
                        （含输入场，以及对照用的 KGO / 原算法结果重网格）

用法（仓库根目录）::

    python orographic_wind_downscaling/cli/preprocess_test_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import xarray as xr
from pyproj import CRS, Transformer
from scipy.interpolate import griddata

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = PACKAGE_ROOT / "test_data" / "wind_calculations_data"
CLI_INPUT_DIR = DATA_DIR / "cli_input"
CLI_INPUT_LATLON_DIR = CLI_INPUT_DIR / "latlon"

# (写出文件名, 主变量名)；源文件位于 DATA_DIR 根目录
INPUT_JOBS = [
    ("input.nc", "wind_speed"),
    ("a_over_s.nc", "silhouette_roughness"),
    ("sigma.nc", "standard_deviation_of_height_in_grid_cell"),
    ("highres_orog.nc", "surface_altitude"),
    ("standard_orog.nc", "surface_altitude"),
    ("veg.nc", "vegetative_roughness_length"),
]

# 方案二对照参考场（同样重网格到 cli_input/latlon/）
LATLON_REF_JOBS = [
    ("kgo.nc", "wind_speed"),
    ("original_algorithm_result.nc", "wind_speed_processed"),
]


def load_primary_dataarray(nc_path: Path, var_name: str) -> xr.DataArray:
    """读取 netCDF 主变量，并写入 grid_mapping_attrs。"""
    ds = xr.open_dataset(nc_path, decode_timedelta=False)
    try:
        if var_name not in ds.data_vars:
            raise ValueError(f"变量 {var_name} 不存在: {nc_path}")
        data = ds[var_name].load()
        grid_mapping_name = data.attrs.get("grid_mapping")
        if not isinstance(grid_mapping_name, str) or grid_mapping_name not in ds.variables:
            for other_name in ds.data_vars:
                cand = ds[other_name].attrs.get("grid_mapping")
                if isinstance(cand, str) and cand in ds.variables:
                    grid_mapping_name = cand
                    break
        if isinstance(grid_mapping_name, str) and grid_mapping_name in ds.variables:
            mapping_attrs_raw = dict(ds[grid_mapping_name].attrs)
            mapping_attrs_json_ready = {}
            for key, value in mapping_attrs_raw.items():
                if isinstance(value, np.ndarray):
                    mapping_attrs_json_ready[key] = value.tolist()
                elif isinstance(value, np.generic):
                    mapping_attrs_json_ready[key] = value.item()
                else:
                    mapping_attrs_json_ready[key] = value
            data.attrs["grid_mapping_attrs"] = json.dumps(
                mapping_attrs_json_ready, ensure_ascii=False
            )
        return data
    finally:
        ds.close()


def _extract_projected_spatial(da: xr.DataArray) -> xr.DataArray:
    """提取投影空间场；保留 level，将 height/投影维重命名为 level/lat/lon。"""
    arr = da
    rename_map = {}
    if "height" in arr.dims:
        rename_map["height"] = "level"
    if "projection_y_coordinate" in arr.dims:
        rename_map["projection_y_coordinate"] = "lat"
    if "projection_x_coordinate" in arr.dims:
        rename_map["projection_x_coordinate"] = "lon"
    if rename_map:
        arr = arr.rename(rename_map)
    keep_dims = ("level", "lat", "lon")
    for dim in list(arr.dims):
        if dim not in keep_dims:
            arr = arr.isel({dim: 0}, drop=True)
    expected_order = [d for d in keep_dims if d in arr.dims]
    return arr.transpose(*expected_order)


def _build_meb6d_from_spatial(spatial: xr.DataArray, *, name: str) -> xr.DataArray:
    units = str(spatial.attrs.get("units", "1"))
    if "level" in spatial.dims:
        level_values = spatial.coords["level"].values.astype(np.float32)
        values = spatial.values[np.newaxis, :, np.newaxis, np.newaxis, :, :].astype(
            np.float32
        )
    else:
        level_values = np.array([0.0], dtype=np.float32)
        values = spatial.values[
            np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
        ].astype(np.float32)
    attrs = {
        "units": units,
        "model": None,
        "dtime_units": "hour",
        "level_type": "height",
        "time_type": "UT",
        "time_bounds": [0, 0],
    }
    grid_mapping_attrs = spatial.attrs.get("grid_mapping_attrs")
    if isinstance(grid_mapping_attrs, str) and grid_mapping_attrs.strip():
        attrs["grid_mapping_attrs"] = grid_mapping_attrs
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array(["data0"], dtype=object),
            "level": level_values,
            "time": np.array(
                [np.datetime64("1970-01-01T00:00:00")], dtype="datetime64[ns]"
            ),
            "dtime": np.array([0], dtype=np.int32),
            "lat": spatial.coords["lat"].copy(deep=True),
            "lon": spatial.coords["lon"].copy(deep=True),
        },
        attrs=attrs,
        name=name,
    )


def build_meb6d_from_projected(nc_path: Path, var_name: str) -> xr.DataArray:
    """方案一：官方投影 nc → 六维 meb（仅维名重命名）。"""
    spatial = _extract_projected_spatial(load_primary_dataarray(nc_path, var_name))
    return _build_meb6d_from_spatial(spatial, name=var_name)


def _regularize_axis(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size < 2:
        return arr
    step = np.nanmedian(np.diff(arr))
    if not np.isfinite(step) or np.isclose(step, 0.0):
        return arr
    return arr[0] + step * np.arange(arr.size, dtype=np.float64)


def _regrid_projected_slice_to_latlon(
    arr2d: xr.DataArray,
    mapping_attrs: dict,
    *,
    method: str = "linear",
) -> xr.DataArray:
    y = np.asarray(arr2d.coords["projection_y_coordinate"].values, dtype=np.float64)
    x = np.asarray(arr2d.coords["projection_x_coordinate"].values, dtype=np.float64)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    transformer = Transformer.from_crs(
        CRS.from_cf(mapping_attrs), CRS.from_epsg(4326), always_xy=True
    )
    lon2d_src, lat2d_src = transformer.transform(xx, yy)
    lat_1d = _regularize_axis(np.nanmean(lat2d_src, axis=1))
    lon_1d = _regularize_axis(np.nanmean(lon2d_src, axis=0))
    lat2d_tgt, lon2d_tgt = np.meshgrid(lat_1d, lon_1d, indexing="ij")
    src_points = np.column_stack([lat2d_src.ravel(), lon2d_src.ravel()])
    src_values = np.asarray(arr2d.values, dtype=np.float64).ravel()
    tgt_points = np.column_stack([lat2d_tgt.ravel(), lon2d_tgt.ravel()])
    interp_values = griddata(src_points, src_values, tgt_points, method=method)
    nan_mask = np.isnan(interp_values)
    if np.any(nan_mask):
        interp_nn = griddata(src_points, src_values, tgt_points, method="nearest")
        interp_values[nan_mask] = interp_nn[nan_mask]
    return xr.DataArray(
        interp_values.reshape(lat2d_tgt.shape).astype(np.float64),
        dims=("lat", "lon"),
        coords={"lat": lat_1d, "lon": lon_1d},
        name=str(arr2d.name or "field"),
        attrs={"units": str(arr2d.attrs.get("units", "1"))},
    )


def projected_da_to_regular_latlon(
    data: xr.DataArray, *, method: str = "linear"
) -> xr.DataArray:
    """投影场 → 规则经纬；已是 lat/lon 则原样整理。"""
    arr = data
    if "height" in arr.dims:
        arr = arr.rename({"height": "level"})
    for dim in list(arr.dims):
        if dim not in (
            "level",
            "projection_y_coordinate",
            "projection_x_coordinate",
            "lat",
            "lon",
        ):
            arr = arr.isel({dim: 0}, drop=True)

    if not {"projection_y_coordinate", "projection_x_coordinate"}.issubset(set(arr.dims)):
        spatial = arr
        if "level" in spatial.dims:
            spatial = spatial.transpose("level", "lat", "lon")
        else:
            spatial = spatial.transpose("lat", "lon")
        return spatial

    mapping_json = arr.attrs.get("grid_mapping_attrs")
    if not isinstance(mapping_json, str) or not mapping_json.strip():
        raise ValueError("缺少 grid_mapping_attrs，无法做投影转经纬重网格。")
    mapping_attrs = json.loads(mapping_json)

    if "level" in arr.dims:
        level_slices = []
        for level_value in arr.coords["level"].values:
            slice_2d = arr.sel(level=level_value).drop_vars("level")
            level_slices.append(
                _regrid_projected_slice_to_latlon(
                    slice_2d, mapping_attrs, method=method
                )
            )
        stacked = xr.concat(level_slices, dim="level")
        stacked = stacked.assign_coords(
            level=arr.coords["level"].values.astype(np.float32)
        )
        return stacked

    return _regrid_projected_slice_to_latlon(arr, mapping_attrs, method=method)


def _ensure_meb6d_spatial_order(data: xr.DataArray) -> xr.DataArray:
    ordered = data.copy(deep=True)
    meb.reset(ordered)
    return ordered


def build_meb6d_from_latlon(nc_path: Path, var_name: str) -> xr.DataArray:
    """方案二：官方投影 nc → 规则经纬六维 meb。"""
    spatial = projected_da_to_regular_latlon(load_primary_dataarray(nc_path, var_name))
    if "grid_mapping_attrs" in spatial.attrs:
        spatial = spatial.copy(deep=True)
        spatial.attrs.pop("grid_mapping_attrs", None)
    meb6d = _build_meb6d_from_spatial(spatial, name=var_name)
    meb6d.attrs["grid_mapping_attrs"] = json.dumps(
        {"grid_mapping_name": "latitude_longitude"},
        ensure_ascii=False,
    )
    return _ensure_meb6d_spatial_order(meb6d)


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


def preprocess_projected_branch() -> None:
    """写出方案一 ``cli_input/``。"""
    CLI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, var_name in INPUT_JOBS:
        src_path = DATA_DIR / filename
        if not src_path.exists():
            raise FileNotFoundError(f"官方样例缺失: {src_path}")
        meb6d = build_meb6d_from_projected(src_path, var_name)
        save_meb6d_to_nc(meb6d, CLI_INPUT_DIR / filename)
    print(f"方案一（投影维重命名）完成: {CLI_INPUT_DIR}")


def preprocess_latlon_branch() -> None:
    """写出方案二 ``cli_input/latlon/``（输入场 + KGO/原结果对照场）。"""
    CLI_INPUT_LATLON_DIR.mkdir(parents=True, exist_ok=True)
    for filename, var_name in INPUT_JOBS + LATLON_REF_JOBS:
        src_path = DATA_DIR / filename
        if not src_path.exists():
            raise FileNotFoundError(f"官方样例缺失: {src_path}")
        meb6d = build_meb6d_from_latlon(src_path, var_name)
        save_meb6d_to_nc(meb6d, CLI_INPUT_LATLON_DIR / filename)
    print(f"方案二（经纬重网格）完成: {CLI_INPUT_LATLON_DIR}")


def main() -> None:
    if not DATA_DIR.is_dir():
        print(
            f"test_data 目录不存在：{DATA_DIR}\n"
            "请补齐官方样例后再运行预处理。"
        )
        return
    print("=== 预处理方案一：投影维重命名 → cli_input/ ===")
    preprocess_projected_branch()
    print("\n=== 预处理方案二：投影→经纬重网格 → cli_input/latlon/ ===")
    preprocess_latlon_branch()
    print("\n全部输入预处理完成。")


if __name__ == "__main__":
    main()
