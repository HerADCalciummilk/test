#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""经纬度输入的等面积投影坐标适配。

在保持格点索引不变的前提下，将等距经纬坐标轴换算为域中心 LAEA 米制坐标，
供核心邻域算法使用；计算结束后再恢复原始经纬坐标标签。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from numpy import ndarray
from pyproj import CRS, Transformer

WGS84_SEMI_MAJOR_AXIS = 6378137.0
WGS84_SEMI_MINOR_AXIS = 6356752.314140356


@dataclass(frozen=True)
class GeographicRegridContext:
    """经纬输入投影坐标适配上下文。"""

    geographic_template: xr.DataArray
    geographic_lat: ndarray
    geographic_lon: ndarray
    projected_lat: ndarray
    projected_lon: ndarray
    projected_mapping_attrs: dict
    geographic_crs: CRS
    projected_crs: CRS


from cf_units import Unit
from numpy import ndarray


def _norm_unit(unit: Optional[str]) -> str:
    return (unit or "").strip().lower()


def _is_distance_unit(unit: Optional[str]) -> bool:
    """判断单位是否为可换算到米的距离单位（非 degree）。"""
    text = _norm_unit(unit)
    if not text or "degree" in text:
        return False
    try:
        Unit(text).convert(1.0, Unit("m"))
        return True
    except Exception:
        return False


def is_projected_spatial_dataarray(data: xr.DataArray) -> bool:
    """判断最后两维是否为米制投影坐标输入。

    meb 约定：常规经纬输入 ``lat/lon`` 可无 ``units``；Improver 兼容投影 meb
    在空间坐标写距离 ``units``，且主变量通常带 ``grid_mapping_attrs``。
    """
    if data.ndim < 2:
        return False
    y_dim, x_dim = data.dims[-2], data.dims[-1]
    if y_dim not in data.coords or x_dim not in data.coords:
        return False
    y_unit = data.coords[y_dim].attrs.get("units")
    x_unit = data.coords[x_dim].attrs.get("units")
    return _is_distance_unit(y_unit) and _is_distance_unit(x_unit)


def is_geographic_spatial_dataarray(data: xr.DataArray) -> bool:
    """判断最后两维是否应按经纬输入处理。

    两维 ``units`` 均为距离单位 → 投影；其余（缺失、degree 等）→ 经纬（meb 默认）。
    """
    if data.ndim < 2:
        return False
    y_dim, x_dim = data.dims[-2], data.dims[-1]
    if y_dim not in data.coords or x_dim not in data.coords:
        return False
    return not is_projected_spatial_dataarray(data)


def _sort_ascending_coords(data: xr.DataArray) -> xr.DataArray:
    """按空间维升序排列。"""
    y_dim, x_dim = data.dims[-2], data.dims[-1]
    return data.sortby(y_dim).sortby(x_dim)


def _build_laea_mapping_attrs(center_lon: float, center_lat: float) -> dict:
    return {
        "grid_mapping_name": "lambert_azimuthal_equal_area",
        "longitude_of_projection_origin": float(center_lon),
        "latitude_of_projection_origin": float(center_lat),
        "false_easting": 0.0,
        "false_northing": 0.0,
        "semi_major_axis": WGS84_SEMI_MAJOR_AXIS,
        "semi_minor_axis": WGS84_SEMI_MINOR_AXIS,
    }


def _build_equal_area_projected_axes(
    lat_values: ndarray,
    lon_values: ndarray,
) -> Tuple[ndarray, ndarray, dict, CRS, CRS]:
    """由等距经纬坐标轴构造对应的 LAEA 米制坐标轴（格点索引不变）。"""
    lat_values = np.asarray(lat_values, dtype=np.float64)
    lon_values = np.asarray(lon_values, dtype=np.float64)
    if lat_values.size < 1 or lon_values.size < 1:
        raise ValueError("经纬坐标长度不足，无法构造投影网格。")

    center_lat = float(np.mean(lat_values))
    center_lon = float(np.mean(lon_values))
    mapping_attrs = _build_laea_mapping_attrs(center_lon, center_lat)
    geographic_crs = CRS.from_epsg(4326)
    projected_crs = CRS.from_cf(mapping_attrs)
    transformer = Transformer.from_crs(geographic_crs, projected_crs, always_xy=True)

    lon_2d, lat_2d = np.meshgrid(lon_values, lat_values)
    proj_x, proj_y = transformer.transform(lon_2d, lat_2d)
    projected_lat = np.mean(np.asarray(proj_y, dtype=np.float64), axis=1)
    projected_lon = np.mean(np.asarray(proj_x, dtype=np.float64), axis=0)

    if projected_lat.size > 1:
        y_spacing = float(np.mean(np.abs(np.diff(projected_lat))))
    else:
        y_spacing = 1000.0
    if projected_lon.size > 1:
        x_spacing = float(np.mean(np.abs(np.diff(projected_lon))))
    else:
        x_spacing = 1000.0
    spacing = float((x_spacing + y_spacing) / 2.0)
    if spacing <= 0.0:
        raise ValueError("无法从经纬网格推断有效的投影网格间距。")

    projected_lat = projected_lat[0] + np.arange(projected_lat.size, dtype=np.float64) * spacing
    projected_lon = projected_lon[0] + np.arange(projected_lon.size, dtype=np.float64) * spacing
    return projected_lat, projected_lon, mapping_attrs, geographic_crs, projected_crs


def build_geographic_regrid_context(data: xr.DataArray) -> GeographicRegridContext:
    """为经纬输入构建投影坐标适配上下文。"""
    if not is_geographic_spatial_dataarray(data):
        raise ValueError("输入不是经纬度空间网格，无法构建投影适配上下文。")

    sorted_data = _sort_ascending_coords(data)
    y_dim, x_dim = sorted_data.dims[-2], sorted_data.dims[-1]
    geographic_lat = np.asarray(sorted_data.coords[y_dim].values, dtype=np.float64)
    geographic_lon = np.asarray(sorted_data.coords[x_dim].values, dtype=np.float64)
    (
        projected_lat,
        projected_lon,
        mapping_attrs,
        geographic_crs,
        projected_crs,
    ) = _build_equal_area_projected_axes(geographic_lat, geographic_lon)

    return GeographicRegridContext(
        geographic_template=sorted_data,
        geographic_lat=geographic_lat,
        geographic_lon=geographic_lon,
        projected_lat=projected_lat,
        projected_lon=projected_lon,
        projected_mapping_attrs=mapping_attrs,
        geographic_crs=geographic_crs,
        projected_crs=projected_crs,
    )


def _projected_spatial_coords(ctx: GeographicRegridContext) -> dict:
    y_dim, x_dim = ctx.geographic_template.dims[-2], ctx.geographic_template.dims[-1]
    return {
        y_dim: xr.DataArray(
            ctx.projected_lat.astype(np.float32),
            dims=(y_dim,),
            attrs={
                "axis": "Y",
                "units": "m",
                "standard_name": "projection_y_coordinate",
            },
        ),
        x_dim: xr.DataArray(
            ctx.projected_lon.astype(np.float32),
            dims=(x_dim,),
            attrs={
                "axis": "X",
                "units": "m",
                "standard_name": "projection_x_coordinate",
            },
        ),
    }


def regrid_dataarray_to_projected(
    data: xr.DataArray, ctx: GeographicRegridContext
) -> xr.DataArray:
    """将经纬 DataArray 的空间坐标轴换算为 LAEA 米制（格点值与拓扑不变）。"""
    sorted_data = _sort_ascending_coords(data)
    coords = dict(sorted_data.coords)
    coords.update(_projected_spatial_coords(ctx))
    attrs = dict(sorted_data.attrs)
    attrs["grid_mapping_attrs"] = json.dumps(
        ctx.projected_mapping_attrs, ensure_ascii=False
    )
    return xr.DataArray(
        np.asarray(sorted_data.values, dtype=np.float32),
        dims=sorted_data.dims,
        coords=coords,
        attrs=attrs,
        name=sorted_data.name,
    )


def regrid_dataarray_to_geographic(
    data: xr.DataArray, ctx: GeographicRegridContext
) -> xr.DataArray:
    """将结果空间坐标轴恢复为原始经纬模板（格点值与拓扑不变）。"""
    sorted_data = _sort_ascending_coords(data)
    template = ctx.geographic_template
    y_dim, x_dim = template.dims[-2], template.dims[-1]
    coords = dict(sorted_data.coords)
    coords[y_dim] = template.coords[y_dim]
    coords[x_dim] = template.coords[x_dim]
    attrs = dict(sorted_data.attrs)
    attrs.pop("grid_mapping_attrs", None)
    return xr.DataArray(
        np.asarray(sorted_data.values, dtype=np.float32),
        dims=sorted_data.dims,
        coords=coords,
        attrs=attrs,
        name=data.name if data.name is not None else template.name,
    )


def prepare_geographic_input(
    data: xr.DataArray,
    mask: Optional[Union[xr.DataArray, ndarray]] = None,
) -> Tuple[xr.DataArray, Optional[Union[xr.DataArray, ndarray]], Optional[GeographicRegridContext]]:
    """若输入为经纬网格，则将空间坐标轴换算为 LAEA 米制。"""
    if not is_geographic_spatial_dataarray(data):
        return data, mask, None

    ctx = build_geographic_regrid_context(data)
    projected_data = regrid_dataarray_to_projected(data, ctx)
    projected_mask = mask
    if isinstance(mask, xr.DataArray):
        projected_mask = regrid_dataarray_to_projected(mask, ctx)
    return projected_data, projected_mask, ctx


def prepare_grid_spacing_dataarray(data: xr.DataArray) -> xr.DataArray:
    """返回用于推断米制格距的 DataArray（空间坐标轴）。

    meb 约定：``lat/lon`` 无 ``units`` 或为度 → 经纬网，经 LAEA 轴换算为米制后推断；
    空间坐标带距离 ``units``（通常与 ``grid_mapping_attrs`` 配套）→ 投影网，直接用原坐标。
    格点值与索引不变，仅替换/换算空间坐标标签供 ``infer_equal_area_grid_spacing_m`` 等使用。
    """
    if is_projected_spatial_dataarray(data):
        return data
    if not is_geographic_spatial_dataarray(data):
        return data
    projected, _, ctx = prepare_geographic_input(data)
    return projected if ctx is not None else data


def restore_geographic_output(
    result: Union[xr.DataArray, ndarray],
    ctx: GeographicRegridContext,
    *,
    template: xr.DataArray,
    name: Optional[str] = None,
    units: Optional[str] = None,
) -> Union[xr.DataArray, ndarray]:
    """将投影坐标轴上的计算结果恢复为原始经纬模板。"""
    if isinstance(result, xr.DataArray):
        geographic = regrid_dataarray_to_geographic(result, ctx)
        if name is not None:
            geographic = geographic.rename(name)
        if units is not None:
            geographic.attrs["units"] = units
        return geographic

    if set(template.dims) == {"member", "level", "time", "dtime", "lat", "lon"}:
        from neighbourhood_probability_processing.utils.utils import rebuild_to_meb_griddata

        output_name = name if name is not None else template.name
        if output_name is None:
            output_name = "neighbourhood_result"
        return rebuild_to_meb_griddata(
            np.asarray(result, dtype=np.float32),
            template,
            name=output_name,
            units=units if units is not None else str(template.attrs.get("units", "")),
        )
    return result
