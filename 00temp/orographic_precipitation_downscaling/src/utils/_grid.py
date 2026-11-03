#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形增强模块网格输入适配与重采样工具。

本模块存放因 xarray / 投影网格输入适配而引入的私有辅助实现，
以及风场解析、标量场重网格所需的坐标与 CRS 推断逻辑。

约定：所有函数以下划线前缀命名，表示模块私有，不应被外部直接导入。
"""

from __future__ import annotations

import json
from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from cf_units import Unit
from pyproj import CRS, Transformer
from scipy.interpolate import RegularGridInterpolator

EARTH_RADIUS_M = 6378137.0  # 地球半径，单位 m
_DEGREE_UNIT_TOKENS = {
    "degrees",
    "degree",
    "deg",
    "°",
    "degrees_north",
    "degree_north",
    "degrees_east",
    "degree_east",
}
_GEOGRAPHIC_MAPPING_NAMES = {"latitude_longitude", "latlon", "geographic"}


def _parse_grid_mapping_attrs(attrs: dict) -> dict:
    """从 ``attrs['grid_mapping_attrs']`` JSON 字符串解析投影参数。"""
    grid_mapping_attrs = attrs.get("grid_mapping_attrs")
    if isinstance(grid_mapping_attrs, str) and grid_mapping_attrs.strip():
        try:
            parsed = json.loads(grid_mapping_attrs)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    return {}


def _norm_unit(unit: Optional[str]) -> str:
    """规范化单位字符串。"""
    return (unit or "").strip().lower()


def _is_distance_unit(unit: Optional[str]) -> bool:
    """判断单位是否可换算到米（排除角度）。"""
    text = _norm_unit(unit)
    if not text or "degree" in text or text in {"deg", "°"}:
        return False
    try:
        Unit(text).convert(1.0, Unit("m"))
        return True
    except Exception:
        return False


def _is_degree_unit(unit: Optional[str]) -> bool:
    """判断单位是否为经纬度（度）。"""
    text = _norm_unit(unit)
    return bool(text) and (text in _DEGREE_UNIT_TOKENS or "degree" in text)


def _mapping_grid_name(data: xr.DataArray) -> str:
    """读取 ``grid_mapping_name``（小写）；无投影元数据时为空串。"""
    mapping = _parse_grid_mapping_attrs(dict(data.attrs))
    return str(mapping.get("grid_mapping_name", "")).strip().lower()


def _values_in_geographic_range(y_values: np.ndarray, x_values: np.ndarray) -> bool:
    """坐标数值是否落在经纬度合理范围内。"""
    y = np.asarray(y_values, dtype=np.float64)
    x = np.asarray(x_values, dtype=np.float64)
    y = y[np.isfinite(y)]
    x = x[np.isfinite(x)]
    if y.size == 0 or x.size == 0:
        return False
    return bool(
        np.nanmax(np.abs(y)) <= 90.0 + 1e-6
        and np.nanmax(np.abs(x)) <= 360.0 + 1e-6
    )


def _is_geographic_spatial(data: xr.DataArray) -> bool:
    """判断空间坐标是否应按真经纬处理。

    与 nbhood / 风速降尺度约定对齐：

    1. 两维均为可换算到米的距离单位 → 投影；
    2. 任一侧为度单位，或 mapping 为 ``latitude_longitude`` → 经纬；
    3. mapping 为投影类 → 非经纬；
    4. **两侧均无 units**：meb 业务默认经纬；例外是数值远超经纬范围
       （投影维仅改名为 ``lat``/``lon`` 的兼容数据）→ 仍按投影米制。
    """
    y_name, x_name = _get_spatial_coord_names(data)
    if y_name not in data.coords or x_name not in data.coords:
        return False
    y_coord = data.coords[y_name]
    x_coord = data.coords[x_name]
    y_units = _norm_unit(y_coord.attrs.get("units"))
    x_units = _norm_unit(x_coord.attrs.get("units"))

    if _is_distance_unit(y_units) and _is_distance_unit(x_units):
        return False
    if _is_degree_unit(y_units) or _is_degree_unit(x_units):
        return True

    mapping_name = _mapping_grid_name(data)
    if mapping_name in _GEOGRAPHIC_MAPPING_NAMES:
        return True
    if mapping_name:
        return False

    y_standard = _norm_unit(y_coord.attrs.get("standard_name"))
    x_standard = _norm_unit(x_coord.attrs.get("standard_name"))
    if y_standard in {"latitude", "grid_latitude"} and x_standard in {
        "longitude",
        "grid_longitude",
    }:
        return True

    units_missing = (not y_units) and (not x_units)
    in_geo_range = _values_in_geographic_range(y_coord.values, x_coord.values)
    if units_missing:
        return in_geo_range
    return in_geo_range


def _mean_abs_diff(values: np.ndarray) -> float:
    """相邻坐标平均间距（绝对值）。"""
    diffs = np.abs(np.diff(np.asarray(values, dtype=np.float64)))
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return 0.0
    return float(np.mean(diffs))


def _geographic_axis_spacing_meters(
    y_values: np.ndarray, x_values: np.ndarray
) -> Tuple[float, float]:
    """经纬坐标轴的南北/东西向格距（米）。

    正球体近似：``dy = R·Δlat``，``dx = R·cos(lat)·Δlon``，``Δ`` 为度。
    """
    dlat = _mean_abs_diff(y_values)
    dlon = _mean_abs_diff(x_values)
    lat_finite = np.asarray(y_values, dtype=np.float64)
    lat_finite = lat_finite[np.isfinite(lat_finite)]
    mean_lat_rad = np.deg2rad(float(np.mean(lat_finite))) if lat_finite.size else 0.0
    dy_m = np.deg2rad(dlat) * EARTH_RADIUS_M
    dx_m = np.deg2rad(dlon) * EARTH_RADIUS_M * np.cos(mean_lat_rad)
    return float(abs(dy_m)), float(abs(dx_m))


def _convert_units(values: np.ndarray, from_unit: str, to_unit: str) -> np.ndarray:
    """使用 cf_units 将 ndarray 从源单位换算到目标单位。

    供无 ``DataArray`` 包装（如坐标 ``values``、numpy 默认单位路径）的场景使用；
    场数据优先使用 ``orographic_precipitation_downscaling.utils.utils.convert_units``。
    """
    from_unit = (from_unit or "").strip()
    to_unit = (to_unit or "").strip()
    if not from_unit or not to_unit or from_unit == to_unit:
        return np.asarray(values)
    vals = np.asarray(values, dtype=np.float64)
    return Unit(from_unit).convert(vals, Unit(to_unit))


def _get_spatial_coord_names(data: xr.DataArray) -> Tuple[str, str]:
    """识别数据中的 y、x 空间坐标名称。"""
    x_name = None
    y_name = None
    for name, coord in data.coords.items():
        axis = str(coord.attrs.get("axis", "")).upper()
        standard_name = _norm_unit(coord.attrs.get("standard_name"))
        if axis == "X" or standard_name in {"projection_x_coordinate", "longitude", "grid_longitude"}:
            x_name = name
        if axis == "Y" or standard_name in {"projection_y_coordinate", "latitude", "grid_latitude"}:
            y_name = name
    if x_name is None or y_name is None:
        dims = list(data.dims)
        if len(dims) < 2:
            raise ValueError("需要至少两个空间维度")
        y_name, x_name = dims[-2], dims[-1]
    return y_name, x_name


def _sort_spatial_dataarray(data: xr.DataArray) -> xr.DataArray:
    """按空间坐标升序排列二维场。"""
    y_name, x_name = _get_spatial_coord_names(data)
    return data.sortby(y_name).sortby(x_name)


def _normalize_to_2d_field(data: Union[xr.DataArray, np.ndarray], name: str) -> Union[xr.DataArray, np.ndarray]:
    """将输入约束为二维单场。

    - ``xarray.DataArray``：标准六维单场（前四维长度均为 1），或已为二维空间场；
    - ``numpy.ndarray``：二维数组。
    """
    if isinstance(data, xr.DataArray):
        if set(data.dims) == {"member", "level", "time", "dtime", "lat", "lon"}:
            normalized = data.transpose("member", "level", "time", "dtime", "lat", "lon")
            for dim in ("member", "level", "time", "dtime"):
                if normalized.sizes[dim] != 1:
                    raise ValueError(
                        f"{name} 仅支持前四维(member/level/time/dtime)长度均为1的六维单场；"
                        f"当前 {dim} 维长度为 {normalized.sizes[dim]}"
                    )
            squeezed = normalized.isel(member=0, level=0, time=0, dtime=0, drop=True)
            if squeezed.ndim != 2:
                raise ValueError(f"{name} 六维单场压缩后不是二维")
            return _sort_spatial_dataarray(squeezed)
        if data.ndim == 2:
            return _sort_spatial_dataarray(data.squeeze(drop=True))
        raise ValueError(
            f"{name} 的 xarray 输入必须是标准六维网格 "
            "(member, level, time, dtime, lat, lon)，或已为二维空间场"
        )
    squeezed = np.asarray(data).squeeze()
    if squeezed.ndim != 2:
        raise ValueError(f"{name} 的 numpy 输入必须是二维场")
    return squeezed


def _prepare_input(data: Union[xr.DataArray, np.ndarray], default_unit: str) -> Tuple[np.ndarray, str, Optional[xr.DataArray]]:
    """统一输入数据的数组值、单位和坐标信息。

    参数
    ----------
    data : Union[xr.DataArray, np.ndarray]
        输入数据，可以是 ``xarray.DataArray`` 或 ``numpy.ndarray`` 。
    default_unit : str
        当输入为 ``numpy.ndarray`` 时使用的默认单位。

    返回值
    -------
    tuple
        - 数值数组
        - 规范化后的单位字符串
        - 原始 ``xarray.DataArray``，若输入不是 xarray 则返回 ``None``
    """
    if isinstance(data, xr.DataArray):
        data = _sort_spatial_dataarray(data) if data.ndim >= 2 else data
        return np.asarray(data.values, dtype=np.float64), (data.attrs.get("units") or "").strip(), data
    return np.asarray(np.asarray(data), dtype=np.float64), (default_unit or "").strip(), None


def _get_data_crs(data: Optional[xr.DataArray]) -> Optional[CRS]:
    """推断数据对应的坐标参考系。

    优先读 ``grid_mapping_attrs``；否则：经纬网格（含业务 meb 无 units）
    视为 WGS84；投影米制且无 mapping 时返回 ``None``。
    """
    if data is None or not isinstance(data, xr.DataArray):
        return None
    mapping_attrs = _parse_grid_mapping_attrs(dict(data.attrs))
    if mapping_attrs:
        try:
            return CRS.from_cf(mapping_attrs)
        except Exception:
            pass
    if _is_geographic_spatial(data):
        return CRS.from_epsg(4326)
    return None


def _coord_values_for_crs(coord: xr.DataArray, crs: Optional[CRS]) -> np.ndarray:
    """按坐标系要求返回可用于计算的坐标值。"""
    values = np.asarray(coord.values, dtype=np.float64)
    units = _norm_unit(coord.attrs.get("units"))
    if crs is not None and crs.is_geographic:
        if units in {"radian", "radians", "rad"}:
            return np.rad2deg(values)
        return values
    if units in {"km", "kilometer", "kilometre"}:
        return values * 1000.0
    return values


def _estimate_grid_spacing_meters(data: Union[xr.DataArray, np.ndarray]) -> float:
    """估算网格的平均空间分辨率（米）。

    ``numpy`` 无坐标，沿用 1 km 默认格距。DataArray 按投影米制或经纬近似换算。
    """
    y_spacing, x_spacing = _grid_spacings_meters(data)
    return float((y_spacing + x_spacing) / 2.0)


def _grid_spacings_meters(data: Union[xr.DataArray, np.ndarray]) -> Tuple[float, float]:
    """分别计算 y、x 方向的网格间距（米）。

    - 投影米制：坐标差分换算到米；
    - 真经纬（含无 units 的业务 meb）：度间距换算为米，东西向按代表纬度缩放；
    - ``numpy``：无坐标对象，默认 ``(1000, 1000)``。
    """
    if not isinstance(data, xr.DataArray):
        return 1000.0, 1000.0
    y_name, x_name = _get_spatial_coord_names(data)
    y_coord = data.coords[y_name]
    x_coord = data.coords[x_name]
    y_values = np.asarray(y_coord.values, dtype=np.float64)
    x_values = np.asarray(x_coord.values, dtype=np.float64)
    if len(y_values) < 2 or len(x_values) < 2:
        return 1000.0, 1000.0

    y_units = y_coord.attrs.get("units")
    x_units = x_coord.attrs.get("units")
    # 两维均为距离单位：投影兼容路径，差分即米制格距
    if _is_distance_unit(y_units) and _is_distance_unit(x_units):
        y_m = _convert_units(y_values, str(y_units).strip(), "m")
        x_m = _convert_units(x_values, str(x_units).strip(), "m")
        return _mean_abs_diff(y_m), _mean_abs_diff(x_m)
    if _is_geographic_spatial(data):
        return _geographic_axis_spacing_meters(y_values, x_values)
    # 无 units 且数值不像经纬：投影维重命名兼容，坐标值按米使用
    return _mean_abs_diff(y_values), _mean_abs_diff(x_values)


def _needs_regridding(source: xr.DataArray, target: xr.DataArray) -> bool:
    """判断源场是否需要重采样到目标网格。"""
    source = _sort_spatial_dataarray(source)
    target = _sort_spatial_dataarray(target)
    source_y, source_x = _get_spatial_coord_names(source)
    target_y, target_x = _get_spatial_coord_names(target)
    if source.shape != target.shape:
        return True
    if not np.array_equal(source.coords[source_y], target.coords[target_y]):
        return True
    if not np.array_equal(source.coords[source_x], target.coords[target_x]):
        return True
    return False


def _regrid_scalar_field(source: xr.DataArray, target: xr.DataArray) -> xr.DataArray:
    """将标量场线性插值到目标网格。

    参数
    ----------
    source : xr.DataArray
        源网格上的标量场。
    target : xr.DataArray
        目标网格模板。

    返回值
    -------
    xr.DataArray
        重采样后的二维标量场。
    """
    source = _sort_spatial_dataarray(source)
    target = _sort_spatial_dataarray(target)
    source_y, source_x = _get_spatial_coord_names(source)
    target_y, target_x = _get_spatial_coord_names(target)
    source_crs = _get_data_crs(source)
    target_crs = _get_data_crs(target)
    source_y_values = _coord_values_for_crs(source.coords[source_y], source_crs)
    source_x_values = _coord_values_for_crs(source.coords[source_x], source_crs)
    target_y_values = _coord_values_for_crs(target.coords[target_y], target_crs)
    target_x_values = _coord_values_for_crs(target.coords[target_x], target_crs)
    target_x_mesh, target_y_mesh = np.meshgrid(target_x_values, target_y_values)
    sample_x = target_x_mesh
    sample_y = target_y_mesh
    # 若无法识别 CRS，则只能按“同一坐标系”假设直接插值；
    # 为避免网格完全不重叠时发生无约束外推，这里做范围检查并显式报错。
    if source_crs is None and target_crs is None:
        y_overlap = (np.max(source_y_values) >= np.min(target_y_values)) and (
            np.max(target_y_values) >= np.min(source_y_values)
        )
        x_overlap = (np.max(source_x_values) >= np.min(target_x_values)) and (
            np.max(target_x_values) >= np.min(source_x_values)
        )
        if not (y_overlap and x_overlap):
            raise ValueError(
                "源网格与目标网格坐标范围不重叠，且缺少 CRS 信息，无法安全重采样。"
            )
    # 投影不一致时，先把目标点反算到源投影，再在源网格上插值。
    if source_crs is not None and target_crs is not None and not source_crs.equals(target_crs):
        transformer = Transformer.from_crs(target_crs, source_crs, always_xy=True)
        sample_x, sample_y = transformer.transform(target_x_mesh, target_y_mesh)
    interpolator = RegularGridInterpolator(
        (source_y_values, source_x_values),
        np.asarray(source.values, dtype=np.float32),
        method="linear",
        bounds_error=False,
        fill_value=np.nan,
    )
    sample_points = np.column_stack([sample_y.ravel(), sample_x.ravel()])
    regridded = interpolator(sample_points).reshape(target.shape).astype(np.float32)
    return xr.DataArray(
        regridded,
        coords={target_y: target.coords[target_y], target_x: target.coords[target_x]},
        dims=(target_y, target_x),
        attrs=source.attrs.copy(),
    )


def _make_field_on_target(values: np.ndarray, units: str, target: xr.DataArray, source_attrs: Optional[dict] = None) -> xr.DataArray:
    """基于目标网格构造新的二维数据场。

    参数
    ----------
    values : np.ndarray
        待写入的数据值。
    units : str
        输出数据单位。
    target : xr.DataArray
        目标网格模板。
    source_attrs : dict, optional
        需要继承的属性字典。

    返回值
    -------
    xr.DataArray
        与目标网格坐标一致的新二维场。
    """
    y_name, x_name = _get_spatial_coord_names(target)
    attrs = dict(source_attrs or {})
    attrs["units"] = units
    if "grid_mapping_attrs" not in attrs:
        target_mapping = target.attrs.get("grid_mapping_attrs")
        if isinstance(target_mapping, str) and target_mapping.strip():
            attrs["grid_mapping_attrs"] = target_mapping
    return xr.DataArray(
        np.asarray(values, dtype=np.float32),
        coords={y_name: target.coords[y_name], x_name: target.coords[x_name]},
        dims=(y_name, x_name),
        attrs=attrs,
    )
