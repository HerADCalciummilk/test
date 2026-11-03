#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方投影样例预处理为 meb，并写出经纬重网格对照输入。

两条路径
--------
1. **投影维重命名**
   ``test_data/orographic_enhancement_data/cli_input/``：投影米制坐标仅改名为
   ``lat``/``lon`` → meb 六维。气象场保留官方 ``height`` 作为 ``level``
   （100/200/500/1000/1500 m），供 ``MetaOrographicEnhancement`` 抽取边界层。

2. **投影→规则经纬重网格**
   每个场按**自身**投影网格转经纬（与原先 Notebook 内嵌逻辑一致，不强制对齐到
   同一张地形网格）。写出：
   - ``.../latlon/cli_input/<同名>.nc``：经纬 **meb 六维**（迁移方法算增强项 / ApplyOE）
   - ``.../latlon/<同名>.nc``：经纬 **Iris Cube**
     （ApplyOE：``precipitation.nc``、``original_algorithm_result.nc``；
     对照：``kgo_hi_res.nc``）。
     气象/地形不写 Cube：原 ``OrographicEnhancement`` 不能在纯经纬上算梯度。
     重网格 KGO 只写 Cube：对照不依赖六维。

约定
----
- 现有 CLI 文件名保持不变：``temperature.nc`` 等
- ``precipitation.nc`` 为 ApplyOE 演示降水（``lwe_precipitation_rate``、``mm hr-1``），
  y 轴与 ``original_algorithm_result.nc`` / ``original_cli_result.nc`` 同向
- meb ``time`` 占位 1970-01-01，与现有 ``cli_input/`` 一致
- 跳过 ``cli_output/``

用法（仓库根目录）::

    python orographic_precipitation_downscaling/cli/preprocess_test_data.py
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

DATA_DIR = PACKAGE_ROOT / "test_data" / "orographic_enhancement_data"
CLI_INPUT_DIR = DATA_DIR / "cli_input"
LATLON_DIR = DATA_DIR / "latlon"
LATLON_MEB_DIR = LATLON_DIR / "cli_input"
DEFAULT_TIME = "1970-01-01T00:00:00"

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
SPHERE_RADIUS = 6371229.0

# (源文件名, 写出文件名, 可选强制变量名, 可选强制单位)
# 气象/地形：方案一 CLI 与方案二经纬都要写
MET_JOBS: Tuple[Tuple[str, str, Optional[str], Optional[str]], ...] = (
    ("temperature.nc", "temperature.nc", None, None),
    ("humidity.nc", "humidity.nc", None, None),
    ("pressure.nc", "pressure.nc", None, None),
    ("wind_speed.nc", "wind_speed.nc", None, None),
    ("wind_direction.nc", "wind_direction.nc", None, None),
    ("orography_uk-standard_1km.nc", "orography_uk-standard_1km.nc", None, None),
)
# 降水叠加演示：降水 + 原方法增强项（ApplyOE）
APPLY_JOBS: Tuple[Tuple[str, str, Optional[str], Optional[str]], ...] = (
    ("precipitation.nc", "precipitation.nc", "lwe_precipitation_rate", "mm hr-1"),
    ("original_algorithm_result.nc", "original_algorithm_result.nc", None, None),
)
# 经纬只写 Cube：重网格 KGO（对照不读 meb）
LATLON_CUBE_ONLY_JOBS: Tuple[Tuple[str, str, Optional[str], Optional[str]], ...] = (
    ("kgo_hi_res.nc", "kgo_hi_res.nc", None, None),
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


def _load_primary(nc_path: Path) -> xr.DataArray:
    """读取主变量（跳过 grid_mapping / bounds）。"""
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
        return primary
    finally:
        ds.close()


def _rename_spatial_and_height(da: xr.DataArray) -> xr.DataArray:
    """投影维改名为 lat/lon；height 改名为 level（气象多层场需要保留）。"""
    rename = {k: v for k, v in SPATIAL_RENAME.items() if k in da.dims}
    if "height" in da.dims:
        rename["height"] = "level"
    if rename:
        da = da.rename(rename)
    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"无法识别空间维: dims={da.dims}")
    return da


def official_to_meb6d(
    nc_path: Path,
    *,
    force_latlon_crs: bool = False,
    da_name: Optional[str] = None,
    units: Optional[str] = None,
    spatial_dtype=np.float32,
    copy_spatial_units: bool = True,
    source: Optional[xr.DataArray] = None,
) -> xr.DataArray:
    """官方/经纬网格场 → meb 六维。多层气象场保留 level，二维场 level 占位 0。"""
    da = source if source is not None else _load_primary(nc_path)
    da = _rename_spatial_and_height(da)

    member_dim = next((d for d in MEMBER_LIKE if d in da.dims), None)
    keep = {member_dim, "level", "lat", "lon"} - {None}
    for dim in list(da.dims):
        if dim not in keep:
            da = da.isel({dim: 0}, drop=True)

    values = _clean_numeric(da.values)
    # 与现有 cli_input 一致：成员名 data0，时刻占位 1970-01-01
    member_coord = np.array(["data0"])
    frt = _to_datetime64(DEFAULT_TIME)
    dtime = 0

    if "level" in da.dims:
        level_coord = np.asarray(da.coords["level"].values, dtype=np.float32)
        if values.ndim == 3:
            work = values[np.newaxis, ...]
        elif values.ndim == 4:
            work = values
        else:
            raise ValueError(f"含 level 时期望 3/4 维，实际 {values.shape}: {nc_path}")
        n_member, n_level, n_lat, n_lon = work.shape
        values_6d = work.reshape(n_member, n_level, 1, 1, n_lat, n_lon).astype(np.float32)
    else:
        level_coord = np.array([0.0], dtype=np.float32)
        if values.ndim != 2:
            raise ValueError(f"期望二维空间场，实际 shape={values.shape}: {nc_path}")
        n_lat, n_lon = values.shape
        values_6d = values.reshape(1, 1, 1, 1, n_lat, n_lon).astype(np.float32)

    attrs: Dict[str, Any] = {
        "units": str(units if units is not None else da.attrs.get("units", "1")),
        "dtime_units": "hour",
        "level_type": "height",
        "time_type": "UT",
        "time_bounds": [0, 0],
        "model": "",
    }
    if force_latlon_crs:
        attrs["grid_mapping_attrs"] = LATLON_GRID_MAPPING
    else:
        gm = da.attrs.get("grid_mapping_attrs")
        if isinstance(gm, str) and gm.strip():
            attrs["grid_mapping_attrs"] = gm

    lat_coord = xr.DataArray(
        np.asarray(da.coords["lat"].values, dtype=spatial_dtype), dims=("lat",)
    )
    lon_coord = xr.DataArray(
        np.asarray(da.coords["lon"].values, dtype=spatial_dtype), dims=("lon",)
    )
    if copy_spatial_units:
        for coord, src_name in ((lat_coord, "lat"), (lon_coord, "lon")):
            src_units = da.coords[src_name].attrs.get("units")
            if src_units:
                coord.attrs["units"] = str(src_units)
            for key in ("axis", "standard_name"):
                if key in da.coords[src_name].attrs:
                    coord.attrs[key] = da.coords[src_name].attrs[key]

    out = xr.DataArray(
        values_6d,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member_coord,
            "level": level_coord,
            "time": np.array([frt], dtype="datetime64[ns]"),
            "dtime": np.array([dtime], dtype=np.int32),
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
    out.attrs["time_bounds"] = [0, 0]
    if force_latlon_crs:
        out.attrs["grid_mapping_attrs"] = LATLON_GRID_MAPPING
    if not out.attrs.get("model"):
        out.attrs["model"] = ""
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

    interp = griddata(src_points[valid], src_values[valid], tgt_points, method=method)
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
    """投影场 → 规则 lat/lon DataArray，保留 level（若有）。"""
    work = da
    if "height" in work.dims:
        work = work.rename({"height": "level"})
    if "projection_y_coordinate" not in work.dims or "projection_x_coordinate" not in work.dims:
        raise ValueError(f"经纬重网格需要投影维，当前 dims={work.dims}")
    mapping_json = work.attrs.get("grid_mapping_attrs")
    if not isinstance(mapping_json, str) or not mapping_json.strip():
        raise ValueError("缺少 grid_mapping_attrs，无法做投影转经纬重网格。")
    mapping_attrs = json.loads(mapping_json)

    for dim in list(work.dims):
        if dim not in ("level", "projection_y_coordinate", "projection_x_coordinate"):
            work = work.isel({dim: 0}, drop=True)

    y = np.asarray(work.coords["projection_y_coordinate"].values, dtype=np.float64)
    x = np.asarray(work.coords["projection_x_coordinate"].values, dtype=np.float64)
    cleaned = _clean_numeric(work.values)

    if "level" in work.dims:
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
            dims=("level", "lat", "lon"),
            coords={
                "level": np.asarray(work.coords["level"].values, dtype=np.float32),
                "lat": lat_1d,
                "lon": lon_1d,
            },
            name=work.name,
            attrs=dict(work.attrs),
        )
    else:
        if cleaned.ndim != 2:
            raise ValueError(f"期望二维投影场，实际 {cleaned.shape}")
        lat_1d, lon_1d, field = _regrid_projected_slice_to_latlon(
            y, x, cleaned, mapping_attrs, method=method
        )
        out = xr.DataArray(
            field.astype(np.float32),
            dims=("lat", "lon"),
            coords={"lat": lat_1d, "lon": lon_1d},
            name=work.name,
            attrs=dict(work.attrs),
        )
    out.attrs.pop("grid_mapping_attrs", None)
    out.attrs.pop("grid_mapping", None)
    return _sort_latlon(out)


def _sort_latlon(da: xr.DataArray) -> xr.DataArray:
    """lat 南→北、lon 西→东，与 meb.reset 方向一致。"""
    out = da
    lat = np.asarray(out.coords["lat"].values)
    lon = np.asarray(out.coords["lon"].values)
    if lat.size > 1 and lat[0] > lat[-1]:
        out = out.isel(lat=slice(None, None, -1))
    if lon.size > 1 and lon[0] > lon[-1]:
        out = out.isel(lon=slice(None, None, -1))
    return out


def _latlon_da_to_cube(da: xr.DataArray, *, name: str, units: str):
    """把规则经纬 DataArray 写成带 GeogCS 的 Iris Cube，供原 ApplyOE 读取。"""
    from cf_units import Unit
    from iris.coord_systems import GeogCS
    from iris.coords import AuxCoord, DimCoord
    from iris.cube import Cube

    geog = GeogCS(SPHERE_RADIUS)
    lat = np.asarray(da.coords["lat"].values, dtype=np.float64)
    lon = np.asarray(da.coords["lon"].values, dtype=np.float64)
    lat_coord = DimCoord(
        lat, standard_name="latitude", units="degrees", coord_system=geog
    )
    lon_coord = DimCoord(
        lon, standard_name="longitude", units="degrees", coord_system=geog
    )
    data = np.asarray(da.values, dtype=np.float32)
    std_names = {
        "air_temperature",
        "relative_humidity",
        "air_pressure",
        "wind_speed",
        "wind_from_direction",
        "surface_altitude",
        "lwe_precipitation_rate",
    }
    cube_kw: Dict[str, Any] = {"units": units}
    if name in std_names:
        cube_kw["standard_name"] = name
    else:
        cube_kw["long_name"] = name

    if data.ndim == 2:
        cube = Cube(
            data,
            dim_coords_and_dims=[(lat_coord, 0), (lon_coord, 1)],
            **cube_kw,
        )
    elif data.ndim == 3:
        z = np.asarray(da.coords["level"].values, dtype=np.float32)
        z_coord = DimCoord(z, standard_name="height", units="m")
        cube = Cube(
            data,
            dim_coords_and_dims=[(z_coord, 0), (lat_coord, 1), (lon_coord, 2)],
            **cube_kw,
        )
    else:
        raise ValueError(f"经纬 Cube 仅支持 2/3 维，实际 {data.shape}")

    # 原 ApplyOrographicEnhancement 按 time 匹配增强项，给一个标准历占位时刻
    cube.add_aux_coord(
        AuxCoord(
            np.array([0.0], dtype=np.float64),
            standard_name="time",
            units=Unit("seconds since 1970-01-01 00:00:00", calendar="standard"),
        )
    )
    return cube


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


def _save_latlon_pair(
    src: Path,
    cube_out: Path,
    meb_out: Path,
    *,
    da_name: Optional[str],
    units: Optional[str],
    write_cube: bool,
    write_meb: bool,
) -> None:
    if not write_cube and not write_meb:
        raise ValueError("write_cube 与 write_meb 至少写一种")
    da = _load_primary(src)
    latlon = regrid_projected_da_to_latlon(da)
    out_name = da_name or str(latlon.name or "field")
    out_units = units if units is not None else str(latlon.attrs.get("units", "1"))
    latlon.name = out_name
    latlon.attrs["units"] = out_units
    if write_cube:
        save_iris_cube(
            _latlon_da_to_cube(latlon, name=out_name, units=out_units),
            cube_out,
        )
    if not write_meb:
        return
    if write_cube:
        meb_source_path = cube_out
        meb_source = None
    else:
        # 原 OE 不能吃纯经纬，气象/地形只写 meb
        meb_source_path = src
        meb_source = latlon
    meb6d = official_to_meb6d(
        meb_source_path,
        force_latlon_crs=True,
        da_name=out_name,
        units=out_units,
        spatial_dtype=np.float64,
        copy_spatial_units=False,
        source=meb_source,
    )
    # 经纬 meb 不再带投影米制坐标的 units
    meb.reset(meb6d)
    save_meb6d(meb6d, meb_out)


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
    if not np.allclose(cube_vals, meb_vals, equal_nan=True, rtol=0.0, atol=1e-5):
        max_abs = float(np.nanmax(np.abs(cube_vals - meb_vals)))
        raise ValueError(f"方案二数值不一致 {cube_path.name}: max_abs={max_abs}")


def preprocess_projected_meb() -> None:
    """投影维重命名 → ``cli_input/``。"""
    jobs = MET_JOBS + APPLY_JOBS
    for src_name, out_name, da_name, units in jobs:
        src = DATA_DIR / src_name
        if not src.exists():
            raise FileNotFoundError(f"官方样例缺失: {src}")
        save_meb6d(
            official_to_meb6d(src, da_name=da_name, units=units, copy_spatial_units=True),
            CLI_INPUT_DIR / out_name,
        )
    print(f"投影 meb 完成：{len(jobs)} 个文件。")


def _run_latlon_jobs(
    jobs: Tuple[Tuple[str, str, Optional[str], Optional[str]], ...],
    *,
    write_cube: bool,
    write_meb: bool,
) -> None:
    for src_name, out_name, da_name, units in jobs:
        src = DATA_DIR / src_name
        if not src.exists():
            raise FileNotFoundError(f"官方样例缺失: {src}")
        _save_latlon_pair(
            src,
            LATLON_DIR / out_name,
            LATLON_MEB_DIR / out_name,
            da_name=da_name,
            units=units,
            write_cube=write_cube,
            write_meb=write_meb,
        )


def preprocess_latlon_branch() -> None:
    """各场独立投影→经纬：气象/地形写 meb；ApplyOE 写 Cube+meb；KGO 只写 Cube。"""
    _run_latlon_jobs(MET_JOBS, write_cube=False, write_meb=True)
    _run_latlon_jobs(APPLY_JOBS, write_cube=True, write_meb=True)
    _run_latlon_jobs(LATLON_CUBE_ONLY_JOBS, write_cube=True, write_meb=False)
    cube_names = sorted(
        {out_name for _, out_name, _, _ in APPLY_JOBS + LATLON_CUBE_ONLY_JOBS}
    )
    print(
        f"经纬 meb 完成：{len(MET_JOBS) + len(APPLY_JOBS)} 个；"
        f"Cube：{', '.join(cube_names)}。"
    )


def _verify_latlon_cube_meb_match() -> None:
    """只抽查同时写出 Cube 的 ApplyOE 场。"""
    for _, out_name, _, _ in APPLY_JOBS:
        _verify_one_latlon_pair(LATLON_DIR / out_name, LATLON_MEB_DIR / out_name)
    print("抽查通过：ApplyOE 经纬 Cube 与 meb 空间场一致。")


def main() -> None:
    print("=== 投影维重命名 → cli_input/ ===")
    preprocess_projected_meb()
    print("\n=== 投影→经纬重网格 → latlon/cli_input/（meb）+ latlon/ Cube ===")
    preprocess_latlon_branch()
    _verify_latlon_cube_meb_match()
    print("\n全部预处理完成。")


if __name__ == "__main__":
    main()
