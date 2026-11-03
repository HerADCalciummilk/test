#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""重网格用的网格处理工具（xr.DataArray 六维接口）。"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray
from numpy.ma.core import MaskedArray
from pyproj import CRS, Transformer
from scipy.interpolate import RegularGridInterpolator

from regrid.src.utils._coords import (
    convert_axis_units_to_meters,
    is_projected_spatial,
    parse_grid_mapping_attrs,
    spatial_axis_values,
    target_points_in_source_crs,
)
from regrid.utils.utils import spatial_coords_match

# 对齐 Iris ``analysis._interpolation.EXTRAPOLATION_MODES`` 的 bounds_error /
# fill_value；DataArray 无 MaskedArray，故省略 mask_fill_value / force_mask，
# nan / mask / nanmask 均填 NaN。
EXTRAPOLATION_MODES = {
    "extrapolate": (False, None),
    "error": (True, None),
    "nan": (False, np.nan),
    "mask": (False, np.nan),
    "nanmask": (False, np.nan),
}


def ensure_ascending_coord(data: xr.DataArray) -> xr.DataArray:
    """若 lat/lon 坐标降序，则排序为升序。"""
    result = data
    for dim in ("lat", "lon"):
        if dim not in result.coords:
            continue
        points = np.asarray(result.coords[dim].values)
        if points.size > 1 and points[0] > points[-1]:
            result = result.sortby(dim)
    return result


def calculate_input_grid_spacing(data_in: xr.DataArray) -> Tuple[float, float]:
    """计算输入源网格的纬向/经向等间距（度）。

    源网格必须是经纬度规则网格（非投影），且坐标升序。
    """
    if is_projected_spatial(data_in):
        raise ValueError("Input grid is not on a latitude/longitude system")

    lat = np.asarray(data_in.coords["lat"].values, dtype=np.float64)
    lon = np.asarray(data_in.coords["lon"].values, dtype=np.float64)
    if lat.size < 2 or lon.size < 2:
        raise ValueError("Input grid must have at least 2 points along lat and lon")

    lat_diffs = np.abs(np.diff(lat))
    lon_diffs = np.abs(np.diff(lon))
    lat_spacing = float(np.mean(lat_diffs))
    lon_spacing = float(np.mean(lon_diffs))
    # 与原算法 rtol=4e-5 一致地检查等间距
    if not np.allclose(lat_diffs, lat_spacing, rtol=4.0e-5, atol=0.0):
        raise ValueError("Coordinate lat points are not equally spaced")
    if not np.allclose(lon_diffs, lon_spacing, rtol=4.0e-5, atol=0.0):
        raise ValueError("Coordinate lon points are not equally spaced")

    if lon[-1] < lon[0] or lat[-1] < lat[0]:
        raise ValueError("Input grid coordinates are not ascending.")
    return lat_spacing, lon_spacing


def latlon_from_dataarray(data: xr.DataArray) -> ndarray:
    """生成展平后的经纬度对数组 (N x 2)。

    - 经纬分支：直接使用 ``lat``/``lon`` 坐标做 meshgrid。
    - 投影分支：按 ``grid_mapping_attrs`` 将投影坐标转换到 WGS84 经纬度。

    对应原版 ``latlon_from_cube``；投影转换对应原版 ``transform_grid_to_lat_lon``。
    """
    lat_vals = np.asarray(data.coords["lat"].values, dtype=np.float64)
    lon_vals = np.asarray(data.coords["lon"].values, dtype=np.float64)
    lat_2d, lon_2d = np.meshgrid(lat_vals, lon_vals, indexing="ij")

    if not is_projected_spatial(data):
        return np.dstack((lat_2d, lon_2d)).reshape((-1, 2)).astype(np.float64)

    mapping = parse_grid_mapping_attrs(dict(data.attrs))
    if not mapping:
        raise ValueError(
            "投影坐标输入缺少可解析的 grid_mapping_attrs，无法转换到经纬度。"
        )
    lat_units = data.coords["lat"].attrs.get("units")
    lon_units = data.coords["lon"].attrs.get("units")
    lat_m = convert_axis_units_to_meters(lat_2d, lat_units, "lat")
    lon_m = convert_axis_units_to_meters(lon_2d, lon_units, "lon")
    source_crs = CRS.from_cf(mapping)
    transformer = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
    lons, lats = transformer.transform(lon_m, lat_m)
    return np.dstack((lats, lons)).reshape((-1, 2)).astype(np.float64)


def unflatten_spatial_dimensions(
    regrid_result: ndarray,
    data_out_mask: xr.DataArray,
    in_values: ndarray,
    lats_index: int,
    lons_index: int,
) -> Union[ndarray, MaskedArray]:
    """将 (lat*lon, ...) 结果恢复为 (..., lat, lon) 形状。"""
    cube_out_dim0 = int(data_out_mask.sizes["lat"])
    cube_out_dim1 = int(data_out_mask.sizes["lon"])
    latlon_shape = [cube_out_dim0, cube_out_dim1] + list(in_values.shape[1:])

    regrid_result = np.reshape(regrid_result, latlon_shape)
    regrid_result = np.swapaxes(regrid_result, 1, lons_index)
    regrid_result = np.swapaxes(regrid_result, 0, lats_index)
    return regrid_result


def flatten_spatial_dimensions(
    data: xr.DataArray,
) -> Tuple[Union[ndarray, MaskedArray], int, int]:
    """将 (..., lat, lon) 展平为 (lat*lon, ...)。"""
    # 约定六维顺序，空间维固定为最后两维
    normalized = meb.checkout_griddata(data, valid_val=(-np.inf, np.inf, np.nan))
    in_values = np.asarray(normalized.values)
    lats_index = list(normalized.dims).index("lat")
    lons_index = list(normalized.dims).index("lon")

    in_values = np.swapaxes(in_values, 0, lats_index)
    in_values = np.swapaxes(in_values, 1, lons_index)

    lats_len = int(in_values.shape[0])
    lons_len = int(in_values.shape[1])
    latlon_shape = [lats_len * lons_len] + list(in_values.shape[2:])
    in_values = np.reshape(in_values, latlon_shape)
    return in_values, lats_index, lons_index


def classify_output_surface_type(data_out_mask: xr.DataArray) -> ndarray:
    """按目标海陆掩码分类目标格点（展平为一维）。"""
    mask_2d = _spatial_2d(data_out_mask)
    return np.asarray(mask_2d).reshape(-1)


def classify_input_surface_type(
    data_in_mask: xr.DataArray, classify_latlons: ndarray
) -> ndarray:
    """将源掩码最近邻插值到给定经纬点，得到海陆分类。"""
    mask_2d = _spatial_2d(data_in_mask)
    in_land_mask_lats = np.asarray(data_in_mask.coords["lat"].values, dtype=np.float64)
    in_land_mask_lons = np.asarray(data_in_mask.coords["lon"].values, dtype=np.float64)

    mask_rg_interp = RegularGridInterpolator(
        (in_land_mask_lats, in_land_mask_lons),
        np.asarray(mask_2d, dtype=np.float64),
        method="nearest",
        bounds_error=False,
        fill_value=0.0,
    )
    return np.bool_(mask_rg_interp(classify_latlons))


def similar_surface_classify(
    in_is_land: ndarray, out_is_land: ndarray, nearest_in_indexes: ndarray
) -> ndarray:
    """判断目标点邻近源点是否与目标同为陆地或同为海洋。"""
    k = nearest_in_indexes.shape[1]
    out_is_land_bcast = np.broadcast_to(
        out_is_land, (k, out_is_land.shape[0])
    ).transpose()

    nearest_is_land = in_is_land[nearest_in_indexes]
    nearest_same_type = np.logical_not(
        np.logical_xor(nearest_is_land, out_is_land_bcast)
    )
    return nearest_same_type


def slice_data_by_domain(
    data_in: xr.DataArray, output_domain: Tuple[float, float, float, float]
) -> xr.DataArray:
    """按目标域裁剪源场（四周各扩 2 个格距）。"""
    lat_max, lon_max, lat_min, lon_min = output_domain
    lat_d, lon_d = calculate_input_grid_spacing(data_in)
    sliced = data_in.sel(
        lat=slice(lat_min - 2.0 * lat_d, lat_max + 2.0 * lat_d),
        lon=slice(lon_min - 2.0 * lon_d, lon_max + 2.0 * lon_d),
    )
    if sliced.sizes["lat"] == 0 or sliced.sizes["lon"] == 0:
        raise ValueError(
            "按目标域裁剪后源场为空：请检查源/目标空间范围是否重叠，"
            "以及投影目标的 grid_mapping_attrs 是否正确。"
        )
    return sliced


def slice_mask_data_by_domain(
    data_in: xr.DataArray,
    data_in_mask: xr.DataArray,
    output_domain: Tuple[float, float, float, float],
) -> Tuple[xr.DataArray, xr.DataArray]:
    """同时裁剪源场与源掩码。"""
    lat_max, lon_max, lat_min, lon_min = output_domain
    lat_d_1, lon_d_1 = calculate_input_grid_spacing(data_in)
    lat_d_2, lon_d_2 = calculate_input_grid_spacing(data_in_mask)
    lat_d = lat_d_1 if lat_d_1 > lat_d_2 else lat_d_2
    lon_d = lon_d_1 if lon_d_1 > lon_d_2 else lon_d_2

    lat_slice = slice(lat_min - 2.0 * lat_d, lat_max + 2.0 * lat_d)
    lon_slice = slice(lon_min - 2.0 * lon_d, lon_max + 2.0 * lon_d)
    sliced_in = data_in.sel(lat=lat_slice, lon=lon_slice)
    sliced_mask = data_in_mask.sel(lat=lat_slice, lon=lon_slice)
    if (
        sliced_in.sizes["lat"] == 0
        or sliced_in.sizes["lon"] == 0
        or sliced_mask.sizes["lat"] == 0
        or sliced_mask.sizes["lon"] == 0
    ):
        raise ValueError(
            "按目标域裁剪后源场/掩码为空：请检查源/目标空间范围是否重叠，"
            "以及投影目标的 grid_mapping_attrs 是否正确。"
        )
    return sliced_in, sliced_mask


def create_regrid_dataarray(
    data_array: ndarray, data_in: xr.DataArray, data_out: xr.DataArray
) -> xr.DataArray:
    """用重网格结果数组组装输出 DataArray。

    - 非空间维与属性继承自 ``data_in``；
    - 空间维坐标继承自 ``data_out``；
    - 投影元数据优先保留目标网格的 ``grid_mapping_attrs``。
    """
    data_in = meb.checkout_griddata(data_in, valid_val=(-np.inf, np.inf, np.nan))
    data_out = meb.checkout_griddata(data_out, valid_val=(-np.inf, np.inf, np.nan))

    # 输出形状：源场前四维 × 目标空间维
    out_shape = (
        data_in.sizes["member"],
        data_in.sizes["level"],
        data_in.sizes["time"],
        data_in.sizes["dtime"],
        data_out.sizes["lat"],
        data_out.sizes["lon"],
    )
    values = np.asarray(data_array)
    if values.shape != out_shape:
        if values.size != int(np.prod(out_shape)):
            raise ValueError(
                f"regrid result shape {values.shape} incompatible with {out_shape}"
            )
        values = values.reshape(out_shape)

    coords = {
        "member": data_in.coords["member"],
        "level": data_in.coords["level"],
        "time": data_in.coords["time"],
        "dtime": data_in.coords["dtime"],
        "lat": data_out.coords["lat"],
        "lon": data_out.coords["lon"],
    }
    attrs = dict(data_in.attrs)
    # 目标为投影网格时，输出应携带目标投影参数
    if "grid_mapping_attrs" in data_out.attrs:
        attrs["grid_mapping_attrs"] = data_out.attrs["grid_mapping_attrs"]
    elif is_projected_spatial(data_out) is False:
        attrs.pop("grid_mapping_attrs", None)

    result = xr.DataArray(
        values.astype(np.float32, copy=False),
        coords=coords,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=data_in.name,
        attrs=attrs,
    )
    return result


def group_target_points_with_source_domain(
    data_in: xr.DataArray, out_latlons: ndarray
) -> Tuple[ndarray, ndarray]:
    """将目标点分为落在源域内/外两类。"""
    lat_coord = np.asarray(data_in.coords["lat"].values)
    lon_coord = np.asarray(data_in.coords["lon"].values)

    in_lat_max, in_lat_min = np.max(lat_coord), np.min(lat_coord)
    in_lon_max, in_lon_min = np.max(lon_coord), np.min(lon_coord)

    lat = out_latlons[:, 0]
    lon = out_latlons[:, 1]

    in_domain_lat = np.logical_and(lat >= in_lat_min, lat <= in_lat_max)
    in_domain_lon = np.logical_and(lon >= in_lon_min, lon <= in_lon_max)
    in_domain = np.logical_and(in_domain_lat, in_domain_lon)

    outside_input_domain_index = np.where(np.logical_not(in_domain))[0]
    inside_input_domain_index = np.where(in_domain)[0]
    return outside_input_domain_index, inside_input_domain_index


def mask_target_points_outside_source_domain(
    total_out_point_num: int,
    outside_input_domain_index: ndarray,
    inside_input_domain_index: ndarray,
    regrid_result: Union[ndarray, MaskedArray],
) -> Union[ndarray, MaskedArray]:
    """对落在源域外的目标点填 NaN（或保留掩码）。"""
    output_shape = [total_out_point_num] + list(regrid_result.shape[1:])
    if isinstance(regrid_result, np.ma.MaskedArray):
        output = np.ma.zeros(output_shape, dtype=np.float32)
        output.mask = np.full(output_shape, True, dtype=bool)
        output.mask[inside_input_domain_index] = regrid_result.mask
        output.data[inside_input_domain_index] = regrid_result.data
    else:
        output = np.zeros(output_shape, dtype=np.float32)
        output[inside_input_domain_index] = regrid_result
        output[outside_input_domain_index] = np.nan
    return output


def _spatial_2d(data: xr.DataArray) -> ndarray:
    """提取二维空间场：六维单场取 squeeze，否则取最后两维均值投影。"""
    normalized = meb.checkout_griddata(data, valid_val=(-np.inf, np.inf, np.nan))
    values = np.asarray(normalized.values)
    # 海陆掩码通常为六维单场；若前四维有长度>1，取首个切片保持与原算法二维掩码一致
    return values.reshape(-1, values.shape[-2], values.shape[-1])[0]


def grid_contains_cutout(grid: xr.DataArray, cutout: xr.DataArray) -> bool:
    """检查 ``cutout`` 的空间域是否包含于 ``grid``。"""
    if spatial_coords_match(grid, cutout):
        return True

    for dim in ("lat", "lon"):
        grid_coord = grid.coords[dim]
        cutout_coord = cutout.coords[dim]
        # 元数据：名称、单位
        if grid_coord.name != cutout_coord.name:
            return False
        if grid_coord.attrs.get("units") != cutout_coord.attrs.get("units"):
            return False
        # 投影参数不一致则视为不同坐标系
        if _parse_mapping_key(grid) != _parse_mapping_key(cutout):
            return False

        grid_points = np.asarray(grid_coord.values, dtype=np.float64)
        cutout_points = np.asarray(cutout_coord.values, dtype=np.float64)
        cutout_start = cutout_points[0]
        find_start = [
            bool(np.isclose(cutout_start, grid_point)) for grid_point in grid_points
        ]
        if not np.any(find_start):
            return False
        start = find_start.index(True)
        end = start + len(cutout_points)
        try:
            if not np.allclose(cutout_points, grid_points[start:end]):
                return False
        except ValueError:
            return False
    return True


def _parse_mapping_key(data: xr.DataArray) -> Optional[str]:
    """提取用于坐标系比对的 grid_mapping 摘要。"""
    mapping = data.attrs.get("grid_mapping_attrs")
    if isinstance(mapping, str) and mapping.strip():
        return mapping.strip()
    return None


def regrid_rectilinear(
    source: xr.DataArray,
    target: xr.DataArray,
    *,
    method: str,
    extrapolation_mode: str = "nanmask",
) -> xr.DataArray:
    """用 RegularGridInterpolator 将源场重网格到目标空间维。

    在源场自身坐标系的规则网上插值：先把目标格点变换到源 CRS，再采样。
    坐标系约定（与项目一致）：
    - 无米制 ``units``、且无投影 ``grid_mapping_attrs`` → 视为经纬（WGS84）；
    - 投影输入须带可解析的 ``grid_mapping_attrs``（仅有米制 units 不够）。

    非空间维形状继承自 ``source``，空间维坐标继承自 ``target``。

    ``extrapolation_mode``：``extrapolate`` / ``error``，以及 ``nan`` /
    ``mask`` / ``nanmask``（三者等效，均填 NaN）；``error`` 在目标点越出源域时
    抛出 ``ValueError``。
    """
    source = meb.checkout_griddata(source, valid_val=(-np.inf, np.inf, np.nan))
    target = meb.checkout_griddata(target, valid_val=(-np.inf, np.inf, np.nan))
    # Iris 风格模式 → RegularGridInterpolator 的 bounds_error / fill_value
    try:
        bounds_error, fill_value = EXTRAPOLATION_MODES[str(extrapolation_mode)]
    except KeyError as err:
        raise ValueError(
            f"Unrecognised extrapolation_mode {extrapolation_mode!r}; "
            f"expected one of {tuple(EXTRAPOLATION_MODES)}"
        ) from err

    # 源轴：经纬用度，投影用米；插值器要求升序
    src_y = spatial_axis_values(source, "lat")
    src_x = spatial_axis_values(source, "lon")
    lat_order = np.argsort(src_y)
    lon_order = np.argsort(src_x)
    src_y_sorted = src_y[lat_order]
    src_x_sorted = src_x[lon_order]

    # 目标点 → 源 CRS（同源则不做变换）
    sample_y, sample_x = target_points_in_source_crs(source, target)
    sample_points = np.column_stack([sample_y.ravel(), sample_x.ravel()])

    src_vals = np.asarray(source.values, dtype=np.float32)
    src_vals = src_vals[..., lat_order, :][..., :, lon_order]

    leading_shape = src_vals.shape[:-2]
    flat_leading = int(np.prod(leading_shape)) if leading_shape else 1
    src_flat = src_vals.reshape(flat_leading, src_vals.shape[-2], src_vals.shape[-1])
    out_spatial = (target.sizes["lat"], target.sizes["lon"])
    out_flat = np.empty((flat_leading,) + out_spatial, dtype=np.float32)

    for i in range(flat_leading):
        interpolator = RegularGridInterpolator(
            (src_y_sorted, src_x_sorted),
            src_flat[i],
            method=method,
            bounds_error=bounds_error,
            fill_value=fill_value,
        )
        out_flat[i] = interpolator(sample_points).reshape(out_spatial)

    out_vals = out_flat.reshape(
        source.sizes["member"],
        source.sizes["level"],
        source.sizes["time"],
        source.sizes["dtime"],
        *out_spatial,
    )

    coords = {
        "member": source.coords["member"],
        "level": source.coords["level"],
        "time": source.coords["time"],
        "dtime": source.coords["dtime"],
        "lat": target.coords["lat"],
        "lon": target.coords["lon"],
    }
    attrs = dict(source.attrs)
    if "grid_mapping_attrs" in target.attrs:
        attrs["grid_mapping_attrs"] = target.attrs["grid_mapping_attrs"]
    elif not is_projected_spatial(target):
        attrs.pop("grid_mapping_attrs", None)

    return xr.DataArray(
        out_vals.astype(np.float32, copy=False),
        coords=coords,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=source.name,
        attrs=attrs,
    )
