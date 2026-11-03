#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方投影样例预处理为 meb 格式，供 nbhood / use_nbhood 测试与 Notebook 使用。

约定（与 ``reliability_calibration`` 一致）：

- 阈值维 ``threshold`` → 六维 ``level``（阈值数值写入 level 坐标）
- 集合维 ``realization`` / ``member`` → 六维 ``member``
- 投影维 ``projection_*`` 仅重命名为 ``lat`` / ``lon``（数值仍为投影米制）
- **地形带 mask / weights**：
  - ``iterate_with_mask``：由迁后 ``GenerateOrographyBandAncils`` /
    ``GenerateTopographicZoneWeights`` 在对应网格上原生生成（六维 meb，带维
    ``level``），与 generate_ancillary 输出一致；
  - ``land_and_sea``：继续使用官方 ``topographic_bands/*`` 与 ``ukvx_landmask``，
    仅做投影维重命名与 meb 六维组装（``topographic_zone`` → ``level``；海陆掩码
    ``level`` 长度为 1），不重算分带（官方 band 与现今 Generate* 对同一 orog/land
    不完全一致，且原方法对 KGO 本就有约 0.05 缝）。
- **经纬分支**：仅 ``iterate_with_mask``——输入场重网格到规则经纬；地形带在经纬
  地形/海陆上再次调用迁后插件生成（不对 weights 做 linear 重网格）。
  ``land_and_sea`` 只保留投影 ``cli_input/``（CLI 验证），不生成经纬。
- 投影路径插件结果再重网格到同一经纬，写出 ``ref_projected_*.nc``（Notebook 有界对照只读）

写出目录::

    neighbourhood_probability_processing/test_data/official_test_nbhood/cli_input/{basic,mask,percentile}/
    neighbourhood_probability_processing/test_data/official_test_nbhood/cli_input/{basic,mask,percentile}/latlon/
    neighbourhood_probability_processing/test_data/official_test_use_nbhood/iterate_with_mask/cli_input/
    neighbourhood_probability_processing/test_data/official_test_use_nbhood/iterate_with_mask/cli_input/latlon/
    neighbourhood_probability_processing/test_data/official_test_use_nbhood/land_and_sea/cli_input/   # 仅投影

用法（仓库根目录）::

    python neighbourhood_probability_processing/cli/preprocess_test_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr
from pyproj import CRS, Transformer
from scipy.interpolate import griddata

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = PACKAGE_ROOT / "test_data" / "official_test_nbhood"
CLI_INPUT_DIR = DATA_DIR / "cli_input"

USE_DATA_DIR = PACKAGE_ROOT / "test_data" / "official_test_use_nbhood"
USE_ITER_ROOT = USE_DATA_DIR / "iterate_with_mask"
USE_LAND_ROOT = USE_DATA_DIR / "land_and_sea"
USE_ITER_CLI_INPUT = USE_ITER_ROOT / "cli_input"
USE_LAND_CLI_INPUT = USE_LAND_ROOT / "cli_input"

PROB_VAR = "probability_of_thickness_of_rainfall_amount_above_threshold"
MASK_VAR = "land_binary_mask"
TEMP_VAR = "air_temperature"

FILL_THRESHOLD = 1.0e20

# 集合语义维 → member；阈值维单独映射到 level
MEMBER_LIKE_DIMS = ("member", "realization", "number", "ensemble_member")
LEVEL_LIKE_DIMS = ("threshold", "level")

# official_test_nbhood：显式变量名
NBHOOD_INPUT_JOBS = [
    ("basic", "input.nc", PROB_VAR, True),
    ("mask", "input.nc", PROB_VAR, True),
    ("mask", "mask.nc", MASK_VAR, True),
    ("mask", "input_masked.nc", PROB_VAR, False),  # 保留填充值供内部掩码路径
    ("percentile", "input_circular_percentile.nc", TEMP_VAR, True),
]

# official_test_use_nbhood：(源, 目标, kind)
# kind: "input" → 六维数据场；"band" → 官方掩码/权重组装（land_and_sea 保留官方数值；
# iterate 的 orographic_* / unfold mask 由末尾 Generate* 覆盖写出）
USE_NBHOOD_JOBS = [
    (USE_ITER_ROOT / "basic" / "input.nc", USE_ITER_CLI_INPUT / "input.nc", "input"),
    (
        USE_ITER_ROOT / "basic_collapse_bands" / "thresholded_input.nc",
        USE_ITER_CLI_INPUT / "thresholded_input.nc",
        "input",
    ),
    (
        USE_LAND_ROOT / "topographic_bands" / "input.nc",
        USE_LAND_CLI_INPUT / "input.nc",
        "input",
    ),
    (
        USE_LAND_ROOT / "topographic_bands" / "topographic_bands_land.nc",
        USE_LAND_CLI_INPUT / "topographic_bands_land.nc",
        "band",
    ),
    (
        USE_LAND_ROOT / "topographic_bands" / "weights_land.nc",
        USE_LAND_CLI_INPUT / "weights_land.nc",
        "band",
    ),
    (
        USE_LAND_ROOT / "no_topographic_bands" / "ukvx_landmask.nc",
        USE_LAND_CLI_INPUT / "ukvx_landmask.nc",
        "band",
    ),
]

# 与 generate_ancillary 官方样例同一投影网（100×100 LAEA）
ANC_WEIGHTS_BASIC = (
    REPO_ROOT
    / "generate_ancillary"
    / "test_data"
    / "generate-topography-bands-weights"
    / "basic"
)

# 官方 use_nbhood 地形带上下界（iris topographic_zone.bounds）
ITER_COLLAPSE_BANDS: Dict[str, Any] = {
    "bounds": [[-500.0, 150.0], [150.0, 300.0], [300.0, 10000.0]],
    "units": "m",
}
ITER_UNFOLD_BANDS: Dict[str, Any] = {
    "bounds": [[-500.0, 0.0], [0.0, 50.0], [50.0, 100.0]],
    "units": "m",
}


def load_primary(
    nc_path: Path,
    var_name: Optional[str] = None,
    *,
    mask_and_scale: bool = True,
) -> xr.DataArray:
    """用 xarray 读取官方/Iris 风格 NetCDF 的主变量（不是 meb 专用读取器）。

    预处理用它读原测试数据，再组装为六维 meb。会跳过 ``*_bnds`` 与
    ``grid_mapping`` 标量，并把投影参数写入 ``grid_mapping_attrs``。
    """
    ds = xr.open_dataset(nc_path, decode_timedelta=False, mask_and_scale=mask_and_scale)
    try:
        if var_name and var_name in ds.data_vars:
            data = ds[var_name].load()
        else:
            data = None
            for name, da in ds.data_vars.items():
                if name.endswith("_bnds"):
                    continue
                if da.ndim == 0 and "grid_mapping_name" in da.attrs:
                    continue
                data = da.load()
                break
            if data is None:
                raise ValueError(f"{nc_path} 中未找到主变量")

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


def _rename_projection_to_latlon(da: xr.DataArray, *, sort_spatial: bool = False) -> xr.DataArray:
    """投影空间维重命名为 lat/lon；可选按坐标排序。"""
    rename_map = {}
    if "projection_y_coordinate" in da.dims:
        rename_map["projection_y_coordinate"] = "lat"
    if "projection_x_coordinate" in da.dims:
        rename_map["projection_x_coordinate"] = "lon"
    if rename_map:
        da = da.rename(rename_map)
    attrs = dict(da.attrs)
    attrs.pop("grid_mapping", None)
    da.attrs = attrs
    if sort_spatial:
        if "lat" in da.dims:
            da = da.sortby("lat")
        if "lon" in da.dims:
            da = da.sortby("lon")
    return da


def _clean_fill_values(values, threshold: float = FILL_THRESHOLD) -> np.ndarray:
    """大填充值与非有限值统一置为 NaN。"""
    out = np.asarray(values, dtype=np.float32).copy()
    out[np.abs(out) >= float(threshold)] = np.nan
    out[~np.isfinite(out)] = np.nan
    return out


def _extract_projected_spatial(
    da: xr.DataArray, *, sort_spatial: bool = False
) -> xr.DataArray:
    """提取投影空间场：保留 member/level 语义维，投影维重命名为 lat/lon。"""
    arr = _rename_projection_to_latlon(da, sort_spatial=sort_spatial)

    keep_dims = set(MEMBER_LIKE_DIMS) | set(LEVEL_LIKE_DIMS) | {"lat", "lon"}
    for dim in list(arr.dims):
        if dim not in keep_dims:
            arr = arr.isel({dim: 0}, drop=True)

    member_dim = next((d for d in MEMBER_LIKE_DIMS if d in arr.dims), None)
    level_dim = next((d for d in LEVEL_LIKE_DIMS if d in arr.dims), None)

    order = []
    if member_dim is not None:
        order.append(member_dim)
    if level_dim is not None:
        order.append(level_dim)
    order.extend(["lat", "lon"])
    return arr.transpose(*order)


def _scalar_or_default(coord_values, default):
    arr = np.asarray(coord_values).ravel()
    return arr[0] if arr.size else default


def _build_meb6d_from_spatial(
    spatial: xr.DataArray,
    *,
    name: str,
    clean_fills: bool = False,
) -> xr.DataArray:
    """由 lat/lon 空间场构造六维 meb；threshold → level，realization → member。"""
    units = str(spatial.attrs.get("units", "1"))
    values = np.asarray(spatial.values, dtype=np.float32)
    if clean_fills:
        values = _clean_fill_values(values)

    member_dim = next((d for d in MEMBER_LIKE_DIMS if d in spatial.dims), None)
    level_dim = next((d for d in LEVEL_LIKE_DIMS if d in spatial.dims), None)

    if member_dim is not None:
        member_coord = np.asarray(spatial.coords[member_dim].values)
        if member_coord.dtype == object or np.issubdtype(member_coord.dtype, np.str_):
            pass
        elif np.issubdtype(member_coord.dtype, np.number):
            member_coord = member_coord.astype(np.int32, copy=False)
        else:
            member_coord = member_coord.astype(str)
    else:
        member_coord = np.array([0], dtype=np.int32)

    # 阈值维优先；若仅为标量 threshold 坐标也写入 level
    if level_dim is not None:
        level_coord = np.asarray(spatial.coords[level_dim].values, dtype=np.float32)
    elif "threshold" in spatial.coords:
        level_coord = np.asarray(
            [_scalar_or_default(spatial.coords["threshold"].values, 0.0)],
            dtype=np.float32,
        )
    else:
        level_coord = np.array([0.0], dtype=np.float32)

    # 整理为 (member, level, lat, lon)
    work = values
    if member_dim is None and level_dim is None:
        if work.ndim != 2:
            raise ValueError(f"期望二维空间场，当前 shape={work.shape}")
        work = work[np.newaxis, np.newaxis, :, :]
    elif member_dim is not None and level_dim is None:
        work = work[:, np.newaxis, :, :]
    elif member_dim is None and level_dim is not None:
        work = work[np.newaxis, :, :, :]

    if work.ndim != 4:
        raise ValueError(
            f"空间场整理失败，期望 4 维 (member,level,lat,lon)，当前 {work.shape}"
        )

    n_member, n_level, n_lat, n_lon = work.shape
    if n_member != member_coord.size:
        raise ValueError(
            f"member 长度不一致: data={n_member}, coord={member_coord.size}"
        )
    if n_level != level_coord.size:
        raise ValueError(
            f"level 长度不一致: data={n_level}, coord={level_coord.size}"
        )

    values_6d = work[:, :, np.newaxis, np.newaxis, :, :].astype(np.float32)

    if "forecast_reference_time" in spatial.coords:
        frt = pd.Timestamp(
            _scalar_or_default(
                spatial.coords["forecast_reference_time"].values,
                "1970-01-01T00:00:00",
            )
        )
    elif "time" in spatial.coords:
        frt = pd.Timestamp(
            _scalar_or_default(spatial.coords["time"].values, "1970-01-01T00:00:00")
        )
    else:
        frt = pd.Timestamp("1970-01-01T00:00:00")

    if "forecast_period" in spatial.coords:
        fp = spatial.coords["forecast_period"]
        fp_val = float(_scalar_or_default(fp.values, 0.0))
        fp_units = str(fp.attrs.get("units", ""))
        dtime = fp_val / 3600.0 if fp_units.startswith("second") else fp_val
    else:
        dtime = 0.0

    attrs = {
        "units": units,
        "model": "",
        "dtime_units": "hour",
        "level_type": "isobaric",
        "time_type": "UT",
        "time_bounds": [0, 0],
    }
    grid_mapping_attrs = spatial.attrs.get("grid_mapping_attrs")
    if isinstance(grid_mapping_attrs, str) and grid_mapping_attrs.strip():
        attrs["grid_mapping_attrs"] = grid_mapping_attrs

    thr_src = None
    if level_dim is not None and level_dim in spatial.coords:
        thr_src = spatial.coords[level_dim]
    elif "threshold" in spatial.coords:
        thr_src = spatial.coords["threshold"]
    if thr_src is not None:
        rel = thr_src.attrs.get("spp__relative_to_threshold") or thr_src.attrs.get(
            "relative_to_threshold"
        )
        if rel:
            attrs["relative_to_threshold"] = str(rel)

    return xr.DataArray(
        values_6d,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member_coord,
            "level": level_coord,
            "time": np.array([np.datetime64(frt.to_datetime64())], dtype="datetime64[ns]"),
            "dtime": np.array([np.int32(round(dtime))], dtype=np.int32),
            "lat": spatial.coords["lat"].copy(deep=True),
            "lon": spatial.coords["lon"].copy(deep=True),
        },
        attrs=attrs,
        name=name,
    )


def build_meb6d_from_projected(
    nc_path: Path,
    var_name: Optional[str] = None,
    *,
    mask_and_scale: bool = True,
    sort_spatial: bool = False,
    clean_fills: bool = False,
) -> xr.DataArray:
    """官方投影 nc → 六维 meb。"""
    spatial = _extract_projected_spatial(
        load_primary(nc_path, var_name, mask_and_scale=mask_and_scale),
        sort_spatial=sort_spatial,
    )
    name = var_name or (spatial.name if spatial.name else "data")
    return _build_meb6d_from_spatial(spatial, name=name, clean_fills=clean_fills)


def normalize_band_file(
    nc_path: Path,
    var_name: Optional[str] = None,
    *,
    sort_spatial: bool = True,
) -> xr.DataArray:
    """官方掩码 / 权重 → 六维 meb（不改写场值）。

    - 含 ``topographic_zone``：带维改为 ``level``，保留上下界与
      ``topographic_zones_include_seapoints`` 等属性。
    - 纯二维海陆掩码（如 ``ukvx_landmask``）：投影维 → lat/lon 后扩成六维
      （``level`` 长度为 1）。CLI 仅在 ``level`` 长度 > 1 时走地形带分支，
      故单层 meb 海陆掩码与二维路径语义一致。
    """
    da = _rename_projection_to_latlon(
        load_primary(nc_path, var_name, mask_and_scale=False),
        sort_spatial=sort_spatial,
    )
    # 保留官方属性（Generate* 路径会另写一套；此处以官方为准）
    keep_attrs = {
        k: v
        for k, v in dict(da.attrs).items()
        if k
        in (
            "topographic_zones_include_seapoints",
            "long_name",
            "units",
            "grid_mapping_attrs",
        )
    }

    if "topographic_zone" in da.dims:
        # 带维并入 meb level，供 ApplyNeighbourhood(coord_for_masking="level")
        zone = da.rename({"topographic_zone": "level"})
        cleaned = _clean_fill_values(zone.values)
        spatial = xr.DataArray(
            cleaned,
            dims=zone.dims,
            coords=zone.coords,
            attrs=dict(zone.attrs),
            name=zone.name,
        )
    else:
        # 二维海陆等：直接进六维组装（level=1）
        cleaned = _clean_fill_values(da.values)
        spatial = xr.DataArray(
            cleaned,
            dims=da.dims,
            coords=da.coords,
            attrs=dict(da.attrs),
            name=da.name,
        )

    meb = _build_meb6d_from_spatial(
        spatial, name=spatial.name or "data", clean_fills=False
    )
    meb = meb.copy(deep=True)
    meb.attrs.update(keep_attrs)
    if not meb.attrs.get("units"):
        meb.attrs["units"] = "1"
    if "topographic_zone" in da.dims or meb.sizes.get("level", 1) > 1:
        meb.attrs["level_type"] = "altitude"

    # 官方 topographic_zone_bnds → level_lower/upper_bound（仅分层带）
    if "topographic_zone" in da.dims or "level" in da.dims:
        with xr.open_dataset(
            nc_path, decode_timedelta=False, mask_and_scale=False
        ) as ds:
            bnds_name = next(
                (
                    n
                    for n in ("topographic_zone_bnds", "level_bnds")
                    if n in ds.variables
                ),
                None,
            )
            if bnds_name is not None:
                bnds = np.asarray(ds[bnds_name].values, dtype=np.float32)
                if bnds.ndim == 2 and bnds.shape[0] == meb.sizes["level"]:
                    meb = meb.assign_coords(
                        level_lower_bound=("level", bnds[:, 0]),
                        level_upper_bound=("level", bnds[:, 1]),
                    )
    return meb



def save_meb6d_to_nc(
    data: xr.DataArray,
    dst_path: Path,
    *,
    preserve_nan_fill: bool = False,
) -> None:
    """写出 NetCDF。

    ``preserve_nan_fill=True`` 时设置 ``_FillValue=None``，避免默认填充改写 NaN
    （与 use_nbhood Notebook 原行为一致）。
    """
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
    ds = normalized.to_dataset(name=var_name)
    encoding = {var_name: {"_FillValue": None}} if preserve_nan_fill else None
    ds.to_netcdf(tmp, encoding=encoding)
    tmp.replace(path)
    print(f"写出: {path}  dims={tuple(normalized.dims)} shape={normalized.shape}")


def _regularize_axis(arr: np.ndarray) -> np.ndarray:
    """将近似等间距轴规整为严格等间距。"""
    arr = np.asarray(arr, dtype=np.float64)
    if arr.size < 2:
        return arr
    step = np.nanmedian(np.diff(arr))
    if not np.isfinite(step) or np.isclose(step, 0.0):
        return arr
    return arr[0] + step * np.arange(arr.size, dtype=np.float64)


def _parse_grid_mapping(attrs: dict) -> dict:
    raw = attrs.get("grid_mapping_attrs")
    if isinstance(raw, str) and raw.strip():
        return json.loads(raw)
    if isinstance(raw, dict) and raw:
        return dict(raw)
    raise ValueError("缺少 grid_mapping_attrs，无法做投影→经纬重网格。")


def _regrid_projected_slice_to_latlon(
    y: np.ndarray,
    x: np.ndarray,
    values2d: np.ndarray,
    mapping_attrs: dict,
    *,
    method: str = "linear",
    target_lat: Optional[np.ndarray] = None,
    target_lon: Optional[np.ndarray] = None,
    fill_nan: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """单层投影 (y,x) → 规则经纬；返回 (lat_1d, lon_1d, field2d)。

    ``fill_nan=True``（默认）：线性插值后的空洞用最近邻补全（适合连续输入场）。
    ``fill_nan=False``：按源场有效性掩码（最近邻）把目标无效区置回 NaN，
    避免把邻域结果的大片缺测填成斜向伪影。
    """
    yy, xx = np.meshgrid(y, x, indexing="ij")
    transformer = Transformer.from_crs(
        CRS.from_cf(mapping_attrs), CRS.from_epsg(4326), always_xy=True
    )
    lon2d_src, lat2d_src = transformer.transform(xx, yy)
    if target_lat is None or target_lon is None:
        lat_1d = _regularize_axis(np.nanmean(lat2d_src, axis=1))
        lon_1d = _regularize_axis(np.nanmean(lon2d_src, axis=0))
    else:
        lat_1d = np.asarray(target_lat, dtype=np.float64)
        lon_1d = np.asarray(target_lon, dtype=np.float64)
    lat2d_tgt, lon2d_tgt = np.meshgrid(lat_1d, lon_1d, indexing="ij")

    src_values = np.asarray(values2d, dtype=np.float64).ravel()
    valid = np.isfinite(src_values)
    src_points = np.column_stack([lat2d_src.ravel(), lon2d_src.ravel()])
    tgt_points = np.column_stack([lat2d_tgt.ravel(), lon2d_tgt.ravel()])

    if not np.any(valid):
        out = np.full(lat2d_tgt.shape, np.nan, dtype=np.float64)
        return lat_1d, lon_1d, out

    interp = griddata(src_points[valid], src_values[valid], tgt_points, method=method)
    if fill_nan:
        nan_mask = np.isnan(interp)
        if np.any(nan_mask):
            interp_nn = griddata(
                src_points[valid], src_values[valid], tgt_points, method="nearest"
            )
            interp[nan_mask] = interp_nn[nan_mask]
    else:
        # 有效性掩码随投影格点映射到经纬；无效源点对应的目标点保持 NaN
        validity = griddata(
            src_points,
            valid.astype(np.float64),
            tgt_points,
            method="nearest",
        )
        if method != "nearest":
            # 非 nearest 时先保证有值，再按掩码裁剪
            nan_mask = np.isnan(interp)
            if np.any(nan_mask):
                interp_nn = griddata(
                    src_points[valid], src_values[valid], tgt_points, method="nearest"
                )
                interp[nan_mask] = interp_nn[nan_mask]
        interp = np.where(validity >= 0.5, interp, np.nan)
    return lat_1d, lon_1d, interp.reshape(lat2d_tgt.shape)


def regrid_projected_da_to_geographic(
    da: xr.DataArray,
    *,
    method: str = "linear",
    target_lat: Optional[np.ndarray] = None,
    target_lon: Optional[np.ndarray] = None,
    fill_nan: bool = True,
) -> xr.DataArray:
    """投影米制 ``lat``/``lon`` DataArray → 真经纬度轴（可对齐到指定目标网格）。

    用于预处理写出 ``latlon/`` 输入，以及投影插件结果对齐到同一经纬网格的对照场。
    对照场请设 ``fill_nan=False``，以免把结果中的缺测区填成伪影。
    """
    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"经纬重网格需要 lat/lon 维，当前 dims={da.dims}")
    mapping_attrs = _parse_grid_mapping(da.attrs)
    y = np.asarray(da.coords["lat"].values, dtype=np.float64)
    x = np.asarray(da.coords["lon"].values, dtype=np.float64)

    leading_dims = [d for d in da.dims if d not in ("lat", "lon")]
    if not leading_dims:
        lat_1d, lon_1d, field = _regrid_projected_slice_to_latlon(
            y,
            x,
            da.values,
            mapping_attrs,
            method=method,
            target_lat=target_lat,
            target_lon=target_lon,
            fill_nan=fill_nan,
        )
        out = xr.DataArray(
            field.astype(np.float32),
            dims=("lat", "lon"),
            coords={
                "lat": xr.DataArray(
                    lat_1d, dims=("lat",), attrs={"units": "degree_north"}
                ),
                "lon": xr.DataArray(
                    lon_1d, dims=("lon",), attrs={"units": "degree_east"}
                ),
            },
            name=da.name,
            attrs={k: v for k, v in dict(da.attrs).items() if k != "grid_mapping_attrs"},
        )
        return out

    stacked = da.stack(_leading=tuple(leading_dims))
    slices = []
    lat_1d = lon_1d = None
    for i in range(stacked.sizes["_leading"]):
        lat_1d, lon_1d, field = _regrid_projected_slice_to_latlon(
            y,
            x,
            np.asarray(stacked.isel(_leading=i).values),
            mapping_attrs,
            method=method,
            target_lat=target_lat if target_lat is not None else lat_1d,
            target_lon=target_lon if target_lon is not None else lon_1d,
            fill_nan=fill_nan,
        )
        # 首片确定目标轴后，后续片对齐到同一轴
        if target_lat is None:
            target_lat = lat_1d
        if target_lon is None:
            target_lon = lon_1d
        slices.append(field.astype(np.float32))

    values = np.stack(slices, axis=0)
    # (leading_flat, lat, lon) → 还原 leading 维
    leading_shape = [stacked.sizes["_leading"], len(lat_1d), len(lon_1d)]
    values = values.reshape(leading_shape)
    # 用 unstack 风格重建：先建 flat DataArray 再 unstack
    flat = xr.DataArray(
        values,
        dims=("_leading", "lat", "lon"),
        coords={
            "_leading": stacked.coords["_leading"],
            "lat": ("lat", lat_1d),
            "lon": ("lon", lon_1d),
        },
    )
    out = flat.unstack("_leading").transpose(*leading_dims, "lat", "lon")
    # 补回非堆叠坐标
    for name, coord in da.coords.items():
        if name in ("lat", "lon"):
            continue
        if name not in out.coords and set(coord.dims).isdisjoint({"lat", "lon"}):
            out = out.assign_coords({name: coord})
    out = out.assign_coords(
        {
            "lat": xr.DataArray(
                lat_1d, dims=("lat",), attrs={"units": "degree_north"}
            ),
            "lon": xr.DataArray(
                lon_1d, dims=("lon",), attrs={"units": "degree_east"}
            ),
        }
    )
    attrs = {k: v for k, v in dict(da.attrs).items() if k != "grid_mapping_attrs"}
    out.attrs = attrs
    out.name = da.name
    return out.astype(np.float32, copy=False)


def preprocess_nbhood() -> None:
    """预处理 official_test_nbhood → cli_input/。"""
    print("=== official_test_nbhood（threshold → level）===")
    print(f"源目录: {DATA_DIR}")
    print(f"输出目录: {CLI_INPUT_DIR}")
    for scenario, filename, var_name, mask_and_scale in NBHOOD_INPUT_JOBS:
        src = DATA_DIR / scenario / filename
        if not src.exists():
            raise FileNotFoundError(f"官方样例缺失: {src}")
        meb6d = build_meb6d_from_projected(
            src, var_name, mask_and_scale=mask_and_scale
        )
        save_meb6d_to_nc(meb6d, CLI_INPUT_DIR / scenario / filename)


def preprocess_use_nbhood() -> None:
    """预处理 official_test_use_nbhood → 各场景 cli_input/。"""
    print("=== official_test_use_nbhood（threshold → level）===")
    print(f"源目录: {USE_DATA_DIR}")
    for src, dst, kind in USE_NBHOOD_JOBS:
        if not src.exists():
            raise FileNotFoundError(f"官方样例缺失: {src}")
        if kind == "input":
            data = build_meb6d_from_projected(
                src,
                None,
                mask_and_scale=True,
                sort_spatial=True,
                clean_fills=True,
            )
        elif kind == "band":
            data = normalize_band_file(src, sort_spatial=True)
        else:
            raise ValueError(f"未知预处理类型: {kind}")
        save_meb6d_to_nc(data, dst, preserve_nan_fill=True)
    print(f"  iterate_with_mask cli_input: {USE_ITER_CLI_INPUT}")
    print(f"  land_and_sea cli_input: {USE_LAND_CLI_INPUT}")
    regenerate_use_nbhood_band_inputs()


def _ensure_distance_units(da: xr.DataArray) -> xr.DataArray:
    """投影 meb 空间坐标补 units=m（迁后 nbhood / ancillary 分支判定用）。"""
    out = da.copy(deep=True)
    out.coords["lat"].attrs["units"] = "m"
    out.coords["lon"].attrs["units"] = "m"
    if not out.attrs.get("units"):
        out.attrs["units"] = "m"
    return out


def _ensure_degree_units(da: xr.DataArray) -> xr.DataArray:
    out = da.copy(deep=True)
    out.coords["lat"].attrs["units"] = "degree_north"
    out.coords["lon"].attrs["units"] = "degree_east"
    if not out.attrs.get("units"):
        out.attrs["units"] = "m"
    return out


def _load_ancillary_orog_land_projected() -> Tuple[xr.DataArray, xr.DataArray]:
    """读取与 use_nbhood 同投影网的地形/海陆（generate_ancillary basic）。"""
    import meteva_base as meb

    orog = meb.read_griddata_from_nc(
        str(ANC_WEIGHTS_BASIC / "cli_inputs" / "input_orog_meb.nc")
    )
    land = meb.read_griddata_from_nc(
        str(ANC_WEIGHTS_BASIC / "cli_inputs" / "input_land_meb.nc")
    )
    return _ensure_distance_units(orog), _ensure_distance_units(land)


def _generate_zone_mask_and_weights(
    orog: xr.DataArray,
    land: xr.DataArray,
    thresholds_dict: Dict[str, Any],
) -> Tuple[xr.DataArray, xr.DataArray]:
    """调用迁后插件生成六维地形带 mask / weights（带维 ``level``）。"""
    from generate_ancillary.src.generate_ancillary import GenerateOrographyBandAncils
    from generate_ancillary.src.generate_topographic_zone_weights import (
        GenerateTopographicZoneWeights,
    )

    mask = GenerateOrographyBandAncils().process(orog, thresholds_dict, land)
    weights = GenerateTopographicZoneWeights().process(orog, thresholds_dict, land)
    return mask, weights


def regenerate_use_nbhood_band_inputs() -> None:
    """用迁后 Generate* 写出 iterate_with_mask 的六维地形带 mask、weights。

    ``land_and_sea`` 的 ``topographic_bands_land`` / ``weights_land`` 已在
    ``USE_NBHOOD_JOBS`` 中由官方文件组装，此处不再覆盖。
    """
    print(
        "=== 用 GenerateOrographyBandAncils / ZoneWeights 写出 "
        "iterate 六维 meb（level 带维）==="
    )
    orog, land = _load_ancillary_orog_land_projected()

    # 对齐空间网：与 thresholded_input 一致
    ref = _load_written_dataarray(USE_ITER_CLI_INPUT / "thresholded_input.nc")
    if not np.allclose(orog.lat.values, ref.lat.values) or not np.allclose(
        orog.lon.values, ref.lon.values
    ):
        raise ValueError(
            "generate_ancillary 地形网与 use_nbhood thresholded_input 空间坐标不一致，"
            "无法对齐地形带输入。"
        )

    jobs = [
        (
            ITER_COLLAPSE_BANDS,
            USE_ITER_CLI_INPUT / "orographic_bands_mask.nc",
            USE_ITER_CLI_INPUT / "orographic_bands_weights.nc",
            "iterate collapse",
        ),
        (
            ITER_UNFOLD_BANDS,
            USE_ITER_CLI_INPUT / "mask.nc",
            None,
            "iterate unfold mask",
        ),
    ]
    for thresholds, mask_path, weights_path, tag in jobs:
        mask_m, weights_m = _generate_zone_mask_and_weights(orog, land, thresholds)
        gm = orog.attrs.get("grid_mapping_attrs")
        if gm:
            mask_m = mask_m.copy(deep=True)
            mask_m.attrs["grid_mapping_attrs"] = gm
            weights_m = weights_m.copy(deep=True)
            weights_m.attrs["grid_mapping_attrs"] = gm
        save_meb6d_to_nc(mask_m, mask_path, preserve_nan_fill=True)
        print(
            f"  [{tag}] mask → {mask_path.name}  "
            f"dims={tuple(mask_m.dims)} level={mask_m.sizes.get('level')}"
        )
        if weights_path is not None:
            save_meb6d_to_nc(weights_m, weights_path, preserve_nan_fill=True)
            print(f"  [{tag}] weights → {weights_path.name}")


def _orog_land_on_geographic_grid(
    target_lat: np.ndarray,
    target_lon: np.ndarray,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """将投影地形/海陆 nearest/linear 映到目标经纬网，供经纬上原生生成地形带。"""
    orog_p, land_p = _load_ancillary_orog_land_projected()
    orog_g = regrid_projected_da_to_geographic(
        orog_p,
        method="linear",
        target_lat=target_lat,
        target_lon=target_lon,
        fill_nan=True,
    )
    land_g = regrid_projected_da_to_geographic(
        land_p,
        method="nearest",
        target_lat=target_lat,
        target_lon=target_lon,
        fill_nan=True,
    )
    # 海陆保持 0/1
    land_g = land_g.copy(deep=True)
    land_g.values = np.where(np.asarray(land_g.values) >= 0.5, 1.0, 0.0).astype(
        np.float32
    )
    return _ensure_degree_units(orog_g), _ensure_degree_units(land_g)


def _load_written_dataarray(path: Path) -> xr.DataArray:
    return xr.open_dataarray(path, decode_timedelta=False).load()


def preprocess_nbhood_latlon() -> None:
    """投影 cli_input → 真经纬 latlon/（跳过内部掩码样例）。"""
    print("=== official_test_nbhood 经纬重网格 → latlon/ ===")
    # basic / percentile
    for scenario, filename in (
        ("basic", "input.nc"),
        ("percentile", "input_circular_percentile.nc"),
    ):
        src = CLI_INPUT_DIR / scenario / filename
        proj = _load_written_dataarray(src)
        geo = regrid_projected_da_to_geographic(proj, method="linear")
        save_meb6d_to_nc(geo, CLI_INPUT_DIR / scenario / "latlon" / filename)

    # mask: 输入与外部掩码对齐到同一经纬网格
    mask_input_proj = _load_written_dataarray(CLI_INPUT_DIR / "mask" / "input.nc")
    mask_input_geo = regrid_projected_da_to_geographic(mask_input_proj, method="linear")
    save_meb6d_to_nc(mask_input_geo, CLI_INPUT_DIR / "mask" / "latlon" / "input.nc")
    mask_proj = _load_written_dataarray(CLI_INPUT_DIR / "mask" / "mask.nc")
    # 掩码借用输入的 mapping（若自身缺失）
    if "grid_mapping_attrs" not in mask_proj.attrs:
        mask_proj = mask_proj.copy(deep=True)
        mask_proj.attrs["grid_mapping_attrs"] = mask_input_proj.attrs["grid_mapping_attrs"]
    mask_geo = regrid_projected_da_to_geographic(
        mask_proj,
        method="nearest",
        target_lat=np.asarray(mask_input_geo.lat.values),
        target_lon=np.asarray(mask_input_geo.lon.values),
    )
    save_meb6d_to_nc(mask_geo, CLI_INPUT_DIR / "mask" / "latlon" / "mask.nc")
    print("经纬分支完成：basic / mask / percentile。")


def preprocess_use_nbhood_latlon() -> None:
    """use_nbhood：仅 iterate_with_mask 投影 cli_input → 真经纬 latlon/。

    ``land_and_sea`` 仅供 CLI 投影验证，不再生成经纬分支。
    """
    print("=== official_test_use_nbhood 经纬重网格 → latlon/（仅 iterate_with_mask）===")

    def _write_input_field(cli_root: Path, input_name: str) -> xr.DataArray:
        inp_proj = _load_written_dataarray(cli_root / input_name)
        out_input = cli_root / "latlon" / input_name
        inp_geo = regrid_projected_da_to_geographic(inp_proj, method="linear")
        save_meb6d_to_nc(inp_geo, out_input, preserve_nan_fill=True)
        return inp_geo

    thr_geo = _write_input_field(USE_ITER_CLI_INPUT, "thresholded_input.nc")
    _write_input_field(USE_ITER_CLI_INPUT, "input.nc")

    tgt_lat = np.asarray(thr_geo.lat.values)
    tgt_lon = np.asarray(thr_geo.lon.values)
    orog_g, land_g = _orog_land_on_geographic_grid(tgt_lat, tgt_lon)

    geo_band_jobs = [
        (
            ITER_COLLAPSE_BANDS,
            USE_ITER_CLI_INPUT / "latlon" / "orographic_bands_mask.nc",
            USE_ITER_CLI_INPUT / "latlon" / "orographic_bands_weights.nc",
            "iterate collapse",
        ),
        (
            ITER_UNFOLD_BANDS,
            USE_ITER_CLI_INPUT / "latlon" / "mask.nc",
            None,
            "iterate unfold",
        ),
    ]
    for thresholds, mask_path, weights_path, tag in geo_band_jobs:
        mask_m, weights_m = _generate_zone_mask_and_weights(orog_g, land_g, thresholds)
        save_meb6d_to_nc(mask_m, mask_path, preserve_nan_fill=True)
        print(f"  [{tag} latlon] mask → {mask_path.name}  dims={tuple(mask_m.dims)}")
        if weights_path is not None:
            save_meb6d_to_nc(weights_m, weights_path, preserve_nan_fill=True)
            print(f"  [{tag} latlon] weights → {weights_path.name}")

    print("经纬分支完成：仅 iterate_with_mask（地形带为迁后插件原生生成）。")


def _ensure_mapping(da: xr.DataArray, mapping_attrs) -> xr.DataArray:
    if da.attrs.get("grid_mapping_attrs"):
        return da
    out = da.copy(deep=True)
    out.attrs["grid_mapping_attrs"] = mapping_attrs
    return out


def _write_projected_result_on_latlon(
    projected_result: xr.DataArray,
    *,
    mapping_attrs,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
    dst: Path,
) -> None:
    """投影路径结果 → 对齐到目标经纬网格并写出（供 Notebook 有界对照只读）。

    结果场常含大片 NaN（掩码无效区），重网格时 ``fill_nan=False``，
    并用 ``nearest`` 保持块状邻域边界，避免线性+最近邻补洞造成斜向伪影。
    """
    mapped = _ensure_mapping(projected_result, mapping_attrs)
    on_ll = regrid_projected_da_to_geographic(
        mapped,
        method="nearest",
        target_lat=target_lat,
        target_lon=target_lon,
        fill_nan=False,
    )
    save_meb6d_to_nc(on_ll, dst, preserve_nan_fill=True)


def preprocess_nbhood_latlon_refs() -> None:
    """对官方投影输入跑插件，结果重网格到 latlon/ 并写出对照场。"""
    from neighbourhood_probability_processing.src.nbhood import (
        GeneratePercentilesFromANeighbourhood,
        NeighbourhoodProcessing,
    )

    print("=== official_test_nbhood 投影结果→经纬对照场 ===")
    radius = 20000.0

    # basic square
    proj = _load_written_dataarray(CLI_INPUT_DIR / "basic" / "input.nc")
    geo = _load_written_dataarray(CLI_INPUT_DIR / "basic" / "latlon" / "input.nc")
    result = NeighbourhoodProcessing("square", radius).process(proj)
    _write_projected_result_on_latlon(
        result,
        mapping_attrs=proj.attrs["grid_mapping_attrs"],
        target_lat=np.asarray(geo.lat.values),
        target_lon=np.asarray(geo.lon.values),
        dst=CLI_INPUT_DIR / "basic" / "latlon" / "ref_projected_square.nc",
    )

    # external mask square
    mask_in = _load_written_dataarray(CLI_INPUT_DIR / "mask" / "input.nc")
    mask_ext = _load_written_dataarray(CLI_INPUT_DIR / "mask" / "mask.nc")
    mask_geo = _load_written_dataarray(CLI_INPUT_DIR / "mask" / "latlon" / "input.nc")
    result = NeighbourhoodProcessing("square", radius).process(mask_in, mask=mask_ext)
    _write_projected_result_on_latlon(
        result,
        mapping_attrs=mask_in.attrs["grid_mapping_attrs"],
        target_lat=np.asarray(mask_geo.lat.values),
        target_lon=np.asarray(mask_geo.lon.values),
        dst=CLI_INPUT_DIR / "mask" / "latlon" / "ref_projected_external_square.nc",
    )

    # percentile 50
    pct_in = _load_written_dataarray(
        CLI_INPUT_DIR / "percentile" / "input_circular_percentile.nc"
    )
    pct_geo = _load_written_dataarray(
        CLI_INPUT_DIR / "percentile" / "latlon" / "input_circular_percentile.nc"
    )
    result = GeneratePercentilesFromANeighbourhood(
        radius, percentiles=[50.0]
    ).process(pct_in)
    _write_projected_result_on_latlon(
        result,
        mapping_attrs=pct_in.attrs["grid_mapping_attrs"],
        target_lat=np.asarray(pct_geo.lat.values),
        target_lon=np.asarray(pct_geo.lon.values),
        dst=CLI_INPUT_DIR / "percentile" / "latlon" / "ref_projected_percentile_50.nc",
    )
    print("nbhood 投影→经纬对照场写出完成。")


def preprocess_use_nbhood_latlon_refs() -> None:
    """use_nbhood：投影插件结果重网格到 latlon/ 对照场。"""
    from neighbourhood_probability_processing.src.use_nbhood import ApplyNeighbourhoodProcessingWithAMask

    print("=== official_test_use_nbhood 投影结果→经纬对照场 ===")
    coord = "level"
    ll_root = USE_ITER_CLI_INPUT / "latlon"

    # collapse square @ 10 km
    proj_in = _load_written_dataarray(USE_ITER_CLI_INPUT / "thresholded_input.nc")
    proj_mask = _load_written_dataarray(USE_ITER_CLI_INPUT / "orographic_bands_mask.nc")
    proj_wts = _load_written_dataarray(USE_ITER_CLI_INPUT / "orographic_bands_weights.nc")
    geo_in = _load_written_dataarray(ll_root / "thresholded_input.nc")
    result = ApplyNeighbourhoodProcessingWithAMask(
        coord, "square", 10000.0, collapse_weights=proj_wts
    ).process(proj_in, proj_mask)
    _write_projected_result_on_latlon(
        result,
        mapping_attrs=proj_in.attrs["grid_mapping_attrs"],
        target_lat=np.asarray(geo_in.lat.values),
        target_lon=np.asarray(geo_in.lon.values),
        dst=ll_root / "ref_projected_square_collapsed.nc",
    )

    # unfolded square @ 20 km
    proj_in2 = _load_written_dataarray(USE_ITER_CLI_INPUT / "input.nc")
    proj_mask2 = _load_written_dataarray(USE_ITER_CLI_INPUT / "mask.nc")
    geo_in2 = _load_written_dataarray(ll_root / "input.nc")
    result2 = ApplyNeighbourhoodProcessingWithAMask(
        coord, "square", 20000.0
    ).process(proj_in2, proj_mask2)
    _write_projected_result_on_latlon(
        result2,
        mapping_attrs=proj_in2.attrs["grid_mapping_attrs"],
        target_lat=np.asarray(geo_in2.lat.values),
        target_lon=np.asarray(geo_in2.lon.values),
        dst=ll_root / "ref_projected_square_unfolded.nc",
    )
    print("use_nbhood 投影→经纬对照场写出完成。")


def main() -> None:
    sample = DATA_DIR / "basic" / "input.nc"
    if not sample.is_file():
        print(
            f"官方样例不存在：{sample}\n"
            "请先补充 test_data 后再运行预处理。"
        )
        return
    print("=== nbhood 官方样例预处理（threshold → level）===\n")
    preprocess_nbhood()
    print()
    preprocess_use_nbhood()
    print()
    preprocess_nbhood_latlon()
    print()
    preprocess_use_nbhood_latlon()
    print()
    preprocess_nbhood_latlon_refs()
    print()
    preprocess_use_nbhood_latlon_refs()
    print("\n全部输入预处理完成（含经纬 latlon/ 与投影结果对照场）。")


if __name__ == "__main__":
    main()
