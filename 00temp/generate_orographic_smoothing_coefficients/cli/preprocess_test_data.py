#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方投影样例预处理为 meb，并写出经纬重网格对照输入。

两条路径
--------
1. **投影维重命名（方案一）**
   ``test_data/cli_inputs/input_orography_meb.nc`` 与 ``input_landmask_meb.nc``：
   投影米制坐标改名为 ``lat``/``lon``，坐标 ``units`` 为米，并写入 ``grid_mapping_attrs``。

2. **投影→规则经纬重网格（方案二）**
   - ``test_data/latlon/orography.nc``、``landmask.nc``：Iris 重网格 Cube
   - ``test_data/latlon/cli_inputs/``：同源 meb（lat/lon 为 float64，不写坐标 units）
   地形 Linear、掩码 Nearest 后按 0.5 二值化；两边共用同一目标网格。

约定
----
- 官方场无时间维，meb ``time`` 占位 2018-04-19T00:00:00
- 方案二分辨率 0.01°；不与投影 KGO 对比（格距不同）
- 跳过 ``kgo.nc`` / 原方法结果 / ``cli_outputs/``

用法（仓库根目录）::

    python generate_orographic_smoothing_coefficients/cli/preprocess_test_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import meteva_base as meb
import numpy as np
import pandas as pd
import xarray as xr
from pyproj import CRS, Transformer
from scipy.interpolate import griddata

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = PACKAGE_ROOT / "test_data"
DEFAULT_TIME = "2018-04-19T00:00:00"
LATLON_RESOLUTION = 0.01
OROG_SRC = DATA_DIR / "orography.nc"
LAND_SRC = DATA_DIR / "landmask.nc"

MEMBER_LIKE = ("realization", "member")
SPATIAL_RENAME = {
    "projection_y_coordinate": "lat",
    "projection_x_coordinate": "lon",
    "latitude": "lat",
    "longitude": "lon",
}
FILL_ABS_THRESHOLD = 1.0e20
LATLON_GRID_MAPPING = json.dumps(
    {"grid_mapping_name": "latitude_longitude"}, ensure_ascii=False
)


def _jsonable(value: Any) -> Any:
    """将 numpy 标量/数组转为可 JSON 序列化的 Python 对象。"""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _to_datetime64(value) -> np.datetime64:
    return np.datetime64(pd.Timestamp(value).to_datetime64())


def _forecast_period_hours(fp_var: xr.DataArray) -> float:
    """``forecast_period`` → 小时；单位以 attrs['units'] 为准。"""
    val = float(np.asarray(fp_var.values).ravel()[0])
    units = str(fp_var.attrs.get("units", "")).lower()
    if units.startswith("second"):
        return val / 3600.0
    if units.startswith("minute"):
        return val / 60.0
    return val


def _clean_numeric(values) -> np.ndarray:
    """MaskedArray / 非有限值 / 极大填充值 → float32 NaN 数组。"""
    if np.ma.isMaskedArray(values):
        arr = np.ma.filled(np.ma.asarray(values, dtype=np.float32), np.nan)
    else:
        arr = np.asarray(values, dtype=np.float32).copy()
    arr[~np.isfinite(arr)] = np.nan
    arr[np.abs(arr) >= FILL_ABS_THRESHOLD] = np.nan
    return arr


def _attach_grid_mapping_attrs(da: xr.DataArray, ds: xr.Dataset) -> None:
    """从 Dataset 中的 grid_mapping 变量拷贝 CRS 到 DataArray attrs。"""
    gm_name = da.attrs.get("grid_mapping")
    if not isinstance(gm_name, str) or gm_name not in ds.variables:
        for other in ds.data_vars:
            cand = ds[other].attrs.get("grid_mapping")
            if isinstance(cand, str) and cand in ds.variables:
                gm_name = cand
                break
    if not isinstance(gm_name, str) or gm_name not in ds.variables:
        return
    raw = {k: _jsonable(v) for k, v in dict(ds[gm_name].attrs).items()}
    da.attrs["grid_mapping_attrs"] = json.dumps(raw, ensure_ascii=False)
    da.attrs.pop("grid_mapping", None)


def _load_primary(nc_path: Path) -> Tuple[xr.DataArray, Optional[np.ndarray]]:
    """读取主变量；返回 (DataArray, 可选 FRT bounds 原始值)。"""
    ds = xr.open_dataset(nc_path, decode_timedelta=False, decode_times=True)
    try:
        primary: Optional[xr.DataArray] = None
        for name, var in ds.data_vars.items():
            if name.endswith("_bnds") or "grid_mapping_name" in var.attrs:
                continue
            if var.ndim == 0:
                continue
            primary = var.load()
            break
        if primary is None:
            raise ValueError(f"未找到主变量: {nc_path}")

        merged_attrs = dict(primary.attrs)
        for key in ("title", "source", "institution", "comment", "units"):
            if key not in merged_attrs and key in ds.attrs:
                merged_attrs[key] = ds.attrs[key]
        primary.attrs = merged_attrs
        _attach_grid_mapping_attrs(primary, ds)

        for coord_name in (
            "forecast_reference_time",
            "forecast_period",
            "height",
            "realization",
            "time",
        ):
            if coord_name in ds.variables and coord_name not in primary.coords:
                primary = primary.assign_coords({coord_name: ds[coord_name]})

        frt_bounds: Optional[np.ndarray] = None
        bounds_name = None
        if "forecast_reference_time" in primary.coords:
            bounds_name = primary.coords["forecast_reference_time"].attrs.get("bounds")
        if not isinstance(bounds_name, str):
            bounds_name = "forecast_reference_time_bnds"
        if bounds_name in ds.variables:
            frt_bounds = np.asarray(ds[bounds_name].values).ravel()

        return primary, frt_bounds
    finally:
        ds.close()


def _extract_frt_and_bounds(
    da: xr.DataArray,
    frt_bounds: Optional[np.ndarray] = None,
) -> Tuple[np.datetime64, Optional[List[str]]]:
    """提取起报点与可选 bounds（写入 attrs 的 ISO 字符串对）。"""
    if "forecast_reference_time" in da.coords:
        frt = _to_datetime64(
            np.asarray(da.coords["forecast_reference_time"].values).ravel()[0]
        )
    elif "time" in da.coords:
        frt = _to_datetime64(np.asarray(da.coords["time"].values).ravel()[0])
    else:
        frt = _to_datetime64(DEFAULT_TIME)

    bounds_iso: Optional[List[str]] = None
    if frt_bounds is not None and np.asarray(frt_bounds).size >= 2:
        b = np.asarray(frt_bounds).ravel()
        b0 = _to_datetime64(b[0])
        b1 = _to_datetime64(b[-1])
        if not (b0 == b1 == frt):
            bounds_iso = [
                np.datetime_as_string(b0),
                np.datetime_as_string(b1),
            ]
    return frt, bounds_iso


# ---------------------------------------------------------------------------
# 方案一：投影维重命名 → meb
# ---------------------------------------------------------------------------


def official_to_meb6d(
    nc_path: Path,
    *,
    force_latlon_crs: bool = False,
    da_name: Optional[str] = None,
    spatial_dtype=np.float32,
    copy_spatial_units: bool = True,
) -> xr.DataArray:
    """官方/经纬 Cube 网格场 → meb 六维 DataArray。"""
    da, frt_bounds = _load_primary(nc_path)

    rename = {k: v for k, v in SPATIAL_RENAME.items() if k in da.dims}
    if rename:
        da = da.rename(rename)
    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"无法识别空间维: {nc_path} dims={da.dims}")

    member_dim = next((d for d in MEMBER_LIKE if d in da.dims), None)
    keep = {member_dim, "lat", "lon"} - {None}
    for dim in list(da.dims):
        if dim not in keep:
            da = da.isel({dim: 0}, drop=True)

    values = _clean_numeric(da.values)

    if member_dim is not None:
        member_coord = np.asarray(da.coords[member_dim].values)
        if np.issubdtype(member_coord.dtype, np.number):
            member_coord = member_coord.astype(np.int32, copy=False)
        work = values[:, np.newaxis, :, :]
    else:
        if "realization" in da.coords:
            m0 = int(np.asarray(da.coords["realization"].values).ravel()[0])
        else:
            m0 = 0
        member_coord = np.array([m0], dtype=np.int32)
        if values.ndim != 2:
            raise ValueError(f"期望二维空间场，实际 shape={values.shape}: {nc_path}")
        work = values[np.newaxis, np.newaxis, :, :]

    level_coord = np.array([0.0], dtype=np.float32)

    frt, time_bounds = _extract_frt_and_bounds(da, frt_bounds)
    if "forecast_period" in da.coords:
        dtime = _forecast_period_hours(da.coords["forecast_period"])
    else:
        dtime = 0.0

    n_member, _, n_lat, n_lon = work.shape
    values_6d = work.reshape(n_member, 1, 1, 1, n_lat, n_lon).astype(np.float32)

    attrs: Dict[str, Any] = {
        "units": str(da.attrs.get("units", "1")),
        "dtime_units": "hour",
        "time_type": "UT",
    }
    for key in ("title", "source", "institution", "comment"):
        if key in da.attrs and da.attrs[key] is not None:
            attrs[key] = da.attrs[key]
    if force_latlon_crs:
        attrs.pop("grid_mapping_attrs", None)
    else:
        gm = da.attrs.get("grid_mapping_attrs")
        if isinstance(gm, str) and gm.strip():
            attrs["grid_mapping_attrs"] = gm
    if time_bounds is not None:
        attrs["time_bounds"] = time_bounds

    lat_coord = xr.DataArray(
        np.asarray(da.coords["lat"].values, dtype=spatial_dtype), dims=("lat",)
    )
    lon_coord = xr.DataArray(
        np.asarray(da.coords["lon"].values, dtype=spatial_dtype), dims=("lon",)
    )
    if copy_spatial_units:
        for coord, src_name in ((lat_coord, "lat"), (lon_coord, "lon")):
            units = da.coords[src_name].attrs.get("units")
            if units:
                coord.attrs["units"] = str(units)

    out = xr.DataArray(
        values_6d,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member_coord,
            "level": level_coord,
            "time": np.array([frt], dtype="datetime64[ns]"),
            "dtime": np.array([np.float32(dtime)], dtype=np.float32),
            "lat": lat_coord,
            "lon": lon_coord,
        },
        attrs=attrs,
        name=da_name or da.name,
    )
    meb.set_griddata_attrs(
        out,
        units=out.attrs.get("units"),
        model_var=out.attrs.get("model_var"),
        dtime_units=out.attrs.get("dtime_units"),
        level_type=out.attrs.get("level_type"),
        time_type=out.attrs.get("time_type"),
        is_default=True,
    )
    if time_bounds is not None:
        out.attrs["time_bounds"] = time_bounds
    else:
        out.attrs.pop("time_bounds", None)
    if force_latlon_crs:
        out.attrs.pop("grid_mapping_attrs", None)
    return out


def save_meb6d(data: xr.DataArray, path: Path) -> None:
    """写出 meb NetCDF（临时文件再替换，避免半截写盘）。"""
    path = Path(path)
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
    print(f"写入 {path.relative_to(PACKAGE_ROOT)}")


# ---------------------------------------------------------------------------
# 方案二：投影 → 规则经纬（Cube + meb）
# ---------------------------------------------------------------------------


def _regularize_axis(values: np.ndarray) -> np.ndarray:
    """用中位步长把近似规则轴规整为严格等差。"""
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size < 2:
        return arr
    step = np.nanmedian(np.diff(arr))
    if not np.isfinite(step) or np.isclose(step, 0.0):
        return arr
    return arr[0] + step * np.arange(arr.size, dtype=np.float64)


def _regrid_projected_slice_to_latlon(
    y: np.ndarray,
    x: np.ndarray,
    values2d: np.ndarray,
    mapping_attrs: dict,
    *,
    method: str = "linear",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """单层投影 (y,x) → 规则经纬；返回 (lat_1d, lon_1d, field2d)。"""
    yy, xx = np.meshgrid(y, x, indexing="ij")
    transformer = Transformer.from_crs(
        CRS.from_cf(mapping_attrs), CRS.from_epsg(4326), always_xy=True
    )
    lon2d_src, lat2d_src = transformer.transform(xx, yy)
    lat_1d = _regularize_axis(np.nanmean(lat2d_src, axis=1))
    lon_1d = _regularize_axis(np.nanmean(lon2d_src, axis=0))
    lat2d_tgt, lon2d_tgt = np.meshgrid(lat_1d, lon_1d, indexing="ij")

    src_values = np.asarray(values2d, dtype=np.float64).ravel()
    valid = np.isfinite(src_values)
    src_points = np.column_stack([lat2d_src.ravel(), lon2d_src.ravel()])
    tgt_points = np.column_stack([lat2d_tgt.ravel(), lon2d_tgt.ravel()])

    if not np.any(valid):
        out = np.full(lat2d_tgt.shape, np.nan, dtype=np.float64)
        return lat_1d, lon_1d, out

    interp = griddata(
        src_points[valid], src_values[valid], tgt_points, method=method
    )
    nan_mask = np.isnan(interp)
    if np.any(nan_mask):
        interp_nn = griddata(
            src_points[valid], src_values[valid], tgt_points, method="nearest"
        )
        interp[nan_mask] = interp_nn[nan_mask]
    return lat_1d, lon_1d, interp.reshape(lat2d_tgt.shape)


def regrid_projected_da_to_latlon(
    da: xr.DataArray, *, method: str = "linear"
) -> xr.DataArray:
    """投影场 → 规则 ``latitude``/``longitude`` DataArray（可含 realization 维）。"""
    if "projection_y_coordinate" not in da.dims or "projection_x_coordinate" not in da.dims:
        raise ValueError(f"经纬重网格需要投影维，当前 dims={da.dims}")
    mapping_json = da.attrs.get("grid_mapping_attrs")
    if not isinstance(mapping_json, str) or not mapping_json.strip():
        raise ValueError("缺少 grid_mapping_attrs，无法做投影转经纬重网格。")
    mapping_attrs = json.loads(mapping_json)

    y = np.asarray(da.coords["projection_y_coordinate"].values, dtype=np.float64)
    x = np.asarray(da.coords["projection_x_coordinate"].values, dtype=np.float64)
    member_dim = next((d for d in MEMBER_LIKE if d in da.dims), None)

    work = da
    for dim in list(work.dims):
        if dim not in {member_dim, "projection_y_coordinate", "projection_x_coordinate"} - {
            None
        }:
            work = work.isel({dim: 0}, drop=True)

    cleaned = _clean_numeric(work.values)

    if member_dim is None:
        if cleaned.ndim != 2:
            raise ValueError(f"期望二维投影场，实际 {cleaned.shape}")
        lat_1d, lon_1d, field = _regrid_projected_slice_to_latlon(
            y, x, cleaned, mapping_attrs, method=method
        )
        out = xr.DataArray(
            field.astype(np.float32),
            dims=("latitude", "longitude"),
            coords={"latitude": lat_1d, "longitude": lon_1d},
            name=work.name,
            attrs=dict(work.attrs),
        )
    else:
        members = np.asarray(work.coords[member_dim].values)
        slices = []
        lat_1d = lon_1d = None
        for i in range(cleaned.shape[0]):
            lat_1d, lon_1d, field = _regrid_projected_slice_to_latlon(
                y, x, cleaned[i], mapping_attrs, method=method
            )
            slices.append(field.astype(np.float32))
        stacked = np.stack(slices, axis=0)
        out = xr.DataArray(
            stacked,
            dims=(member_dim, "latitude", "longitude"),
            coords={
                member_dim: members,
                "latitude": lat_1d,
                "longitude": lon_1d,
            },
            name=work.name,
            attrs=dict(work.attrs),
        )

    for name in (
        "forecast_reference_time",
        "forecast_period",
        "height",
        "time",
        "realization",
    ):
        if name in da.coords and name not in out.coords and name not in out.dims:
            out = out.assign_coords({name: da.coords[name]})
    out.attrs.pop("grid_mapping_attrs", None)
    out.attrs.pop("grid_mapping", None)
    return out


def build_regular_latlon_target(cube, resolution: float = LATLON_RESOLUTION, sphere_radius: float = 6371229.0):
    """由投影场角点范围构造统一规则经纬目标网格。"""
    import cartopy.crs as ccrs
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube

    cs = cube.coord_system()
    if cs is None:
        raise ValueError("Cube 没有坐标系统，无法投影到经纬。")
    src_crs = cs.as_cartopy_crs()
    target_crs = ccrs.PlateCarree()
    y_coord = cube.coord(axis="y")
    x_coord = cube.coord(axis="x")
    xx, yy = np.meshgrid(
        [x_coord.points[0], x_coord.points[-1]],
        [y_coord.points[0], y_coord.points[-1]],
    )
    transform = target_crs.transform_points(src_crs, xx, yy)
    lat_min, lat_max = float(transform[:, :, 1].min()), float(transform[:, :, 1].max())
    lon_min, lon_max = float(transform[:, :, 0].min()), float(transform[:, :, 0].max())
    target_lat = np.arange(lat_min, lat_max + resolution * 0.5, resolution)
    target_lon = np.arange(lon_min, lon_max + resolution * 0.5, resolution)
    geog = GeogCS(sphere_radius)
    lat_coord = DimCoord(
        target_lat, standard_name="latitude", units="degrees", coord_system=geog
    )
    lon_coord = DimCoord(
        target_lon, standard_name="longitude", units="degrees", coord_system=geog
    )
    return Cube(
        np.zeros((target_lat.size, target_lon.size), dtype=np.float32),
        dim_coords_and_dims=[(lat_coord, 0), (lon_coord, 1)],
    )


def regrid_to_target(cube, target_grid, *, scheme: str = "linear"):
    from iris.analysis import Linear, Nearest

    if scheme == "nearest":
        regridder = Nearest(extrapolation_mode="extrapolate")
    else:
        regridder = Linear(extrapolation_mode="extrapolate")
    return cube.regrid(target_grid, regridder)


def save_iris_cube(cube, path: Path) -> None:
    """写出 Iris Cube NetCDF。"""
    import iris

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.stem}.tmp.nc"
    if tmp.exists():
        tmp.unlink()
    iris.save(cube, str(tmp))
    try:
        tmp.replace(path)
    except PermissionError as err:
        raise PermissionError(
            f"无法覆盖 {path}（可能被 Jupyter 或其他进程占用）。"
            f"临时文件已写至 {tmp}，请关闭占用后重试。"
        ) from err
    print(f"写入 {path.relative_to(PACKAGE_ROOT)}")


# ---------------------------------------------------------------------------
# 批处理入口
# ---------------------------------------------------------------------------


def _save_latlon_pair(cube, cube_out: Path, meb_out: Path) -> None:
    save_iris_cube(cube, cube_out)
    save_meb6d(
        official_to_meb6d(
            cube_out,
            force_latlon_crs=True,
            spatial_dtype=np.float64,
            copy_spatial_units=False,
        ),
        meb_out,
    )


def _verify_one_latlon_pair(cube_path: Path, meb_path: Path) -> None:
    import iris

    cube = iris.load_cube(str(cube_path))
    ds = xr.open_dataset(meb_path, decode_timedelta=False)
    try:
        var_name = next(
            name
            for name, var in ds.data_vars.items()
            if var.ndim >= 2 and "grid_mapping_name" not in var.attrs
        )
        meb_vals = np.squeeze(np.asarray(ds[var_name].values, dtype=np.float64))
    finally:
        ds.close()
    cube_vals = np.ma.filled(np.ma.asarray(cube.data, dtype=np.float64), np.nan)
    if cube_vals.shape != meb_vals.shape:
        raise ValueError(
            f"方案二形状不一致 {cube_path.name}: cube={cube_vals.shape}, meb={meb_vals.shape}"
        )
    if not np.allclose(cube_vals, meb_vals, equal_nan=True, rtol=0.0, atol=0.0):
        max_abs = float(np.nanmax(np.abs(cube_vals - meb_vals)))
        raise ValueError(f"方案二数值不一致 {cube_path.name}: max_abs={max_abs}")


def preprocess_projected_meb() -> None:
    """方案一：投影维重命名 → ``cli_inputs/``。"""
    jobs = [
        (OROG_SRC, "input_orography_meb.nc"),
        (LAND_SRC, "input_landmask_meb.nc"),
    ]
    for src, meb_name in jobs:
        if not src.exists():
            raise FileNotFoundError(f"官方样例缺失: {src}")
        save_meb6d(
            official_to_meb6d(src, copy_spatial_units=True),
            DATA_DIR / "cli_inputs" / meb_name,
        )
    print("方案一完成：2 个 meb 文件。")


def preprocess_latlon_branch() -> None:
    """方案二：Iris 规则经纬重网格 → ``latlon/`` + ``latlon/cli_inputs/``。"""
    import iris

    orog_cube = iris.load_cube(str(OROG_SRC))
    land_cube = iris.load_cube(str(LAND_SRC))
    target = build_regular_latlon_target(orog_cube)
    orog_ll = regrid_to_target(orog_cube, target, scheme="linear")
    land_ll = regrid_to_target(land_cube, target, scheme="nearest")
    # 最近邻后按 0.5 阈值恢复二值海陆掩码
    land_bin = (np.ma.filled(np.ma.asarray(land_ll.data, dtype=np.float32), np.nan) >= 0.5).astype(
        np.float32
    )
    land_ll.data = land_bin
    _save_latlon_pair(
        orog_ll,
        DATA_DIR / "latlon" / OROG_SRC.name,
        DATA_DIR / "latlon" / "cli_inputs" / "input_orography_meb.nc",
    )
    _save_latlon_pair(
        land_ll,
        DATA_DIR / "latlon" / LAND_SRC.name,
        DATA_DIR / "latlon" / "cli_inputs" / "input_landmask_meb.nc",
    )
    print("方案二完成：2 组 Cube+meb 经纬文件。")


def _verify_latlon_cube_meb_match() -> None:
    pairs = [
        (
            DATA_DIR / "latlon" / "orography.nc",
            DATA_DIR / "latlon" / "cli_inputs" / "input_orography_meb.nc",
        ),
        (
            DATA_DIR / "latlon" / "landmask.nc",
            DATA_DIR / "latlon" / "cli_inputs" / "input_landmask_meb.nc",
        ),
    ]
    for cube_path, meb_path in pairs:
        _verify_one_latlon_pair(cube_path, meb_path)
    print("抽查通过：方案二 Cube 与 meb 空间场一致。")


def main() -> None:
    if not OROG_SRC.is_file():
        print(
            f"官方样例不存在：{OROG_SRC}\n"
            "请先补充 test_data 后再运行预处理。"
        )
        return
    print("=== 方案一：投影维重命名 → cli_inputs/ ===")
    preprocess_projected_meb()
    print("\n=== 方案二：投影→经纬重网格 → latlon/ + latlon/cli_inputs/ ===")
    preprocess_latlon_branch()
    _verify_latlon_cube_meb_match()
    print("\n全部预处理完成。")


if __name__ == "__main__":
    main()
