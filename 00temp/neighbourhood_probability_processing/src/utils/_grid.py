#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""邻域算法网格间距与坐标单位换算。

投影米制坐标（m/km）用于核心邻域计算；经纬输入在计算前由 ``_regrid`` 将坐标轴
换算为 LAEA 米制。本模块仅处理已进入投影米制坐标轴后的间距推断。
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from cf_units import Unit
from numpy import ndarray

from neighbourhood_probability_processing.src.utils._regrid import is_projected_spatial_dataarray


def _convert_coord_values(
    values: ndarray,
    unit: Optional[str],
    to_unit: str,
    context: str,
) -> ndarray:
    """将坐标数值数组换算到目标单位（cf_units）。"""
    if unit is None or str(unit).strip() == "":
        raise ValueError(f"{context} 必须显式提供 units")
    from_unit = str(unit).strip()
    try:
        source = Unit(from_unit)
        target = Unit(to_unit)
        return np.asarray(
            source.convert(np.asarray(values, dtype=np.float64), target)
        )
    except Exception as exc:
        raise ValueError(
            f"无法将 {context} 单位 {from_unit!r} 换算为 {to_unit!r}: {exc}"
        ) from exc


def _get_xarray_spatial_coords(data: xr.DataArray) -> Tuple[ndarray, ndarray]:
    """获取 xarray 最后两个空间坐标。"""
    if data.ndim < 2:
        raise ValueError("输入数据至少需要两个空间维度")
    y_dim, x_dim = data.dims[-2], data.dims[-1]
    if y_dim not in data.coords or x_dim not in data.coords:
        raise ValueError("xarray 输入最后两个维度必须具有同名一维坐标")
    y_coord = data.coords[y_dim]
    x_coord = data.coords[x_dim]
    if y_coord.ndim != 1 or x_coord.ndim != 1:
        raise ValueError("空间坐标必须为一维")
    return np.asarray(y_coord.values), np.asarray(x_coord.values)


def _calculate_equal_spacing(
    points: ndarray, unit: Optional[str], coord_name: str
) -> float:
    """检查一维坐标是否等间距并返回米制间距。"""
    points_in_metres = _convert_coord_values(points, unit, "m", "空间坐标")
    diffs = np.abs(np.diff(points_in_metres))
    if diffs.size == 0:
        raise ValueError(f"{coord_name} 坐标长度不足，无法计算网格间距")
    spacing = float(np.mean(diffs))
    if not np.allclose(diffs, spacing, rtol=1.0e-5, atol=0.0):
        raise ValueError(f"{coord_name} 坐标不是等间距网格")
    return spacing


def _infer_grid_spacing_from_xarray(
    data: xr.DataArray,
) -> Tuple[float, ndarray, ndarray]:
    """从 xarray 自动推断米制投影网格间距与空间坐标（米）。"""
    if not is_projected_spatial_dataarray(data):
        raise ValueError(
            "空间坐标须为可换算到米的距离单位；"
            "经纬输入应在邻域计算前经 _regrid 适配为投影米制坐标。"
        )

    y_dim, x_dim = data.dims[-2], data.dims[-1]
    y_coord = data.coords[y_dim]
    x_coord = data.coords[x_dim]
    y_points, x_points = _get_xarray_spatial_coords(data)
    y_unit = y_coord.attrs.get("units")
    x_unit = x_coord.attrs.get("units")

    y_spacing = _calculate_equal_spacing(y_points, y_unit, y_dim)
    x_spacing = _calculate_equal_spacing(x_points, x_unit, x_dim)
    if not np.isclose(y_spacing, x_spacing):
        raise ValueError("x 和 y 方向的网格间距必须一致")
    y_metres = _convert_coord_values(y_points, y_unit, "m", "空间坐标")
    x_metres = _convert_coord_values(x_points, x_unit, "m", "空间坐标")
    return x_spacing, y_metres, x_metres


def _parse_grid_spacing(
    grid_spacing: Optional[Union[float, Tuple[float, float]]]
) -> Tuple[float, float]:
    """解析显式传入的网格间距（米）。"""
    if grid_spacing is None:
        raise ValueError("numpy.ndarray 输入必须显式提供 grid_spacing")
    if np.isscalar(grid_spacing):
        spacing = float(grid_spacing)
        if spacing <= 0:
            raise ValueError("grid_spacing 必须为正数")
        return spacing, spacing
    if len(grid_spacing) != 2:
        raise ValueError("grid_spacing 必须是标量或长度为 2 的序列")
    y_spacing = float(grid_spacing[0])
    x_spacing = float(grid_spacing[1])
    if y_spacing <= 0 or x_spacing <= 0:
        raise ValueError("grid_spacing 必须为正数")
    return y_spacing, x_spacing


def _distance_to_number_of_grid_cells(radius: float, grid_spacing: float) -> int:
    """根据半径与网格间距计算网格点数。"""
    if radius <= 0:
        raise ValueError(f"邻域半径必须为正数，当前值为 {radius} 米")
    grid_cells = int(np.ceil(radius / grid_spacing))
    if grid_cells == 0:
        raise ValueError(f"邻域半径 {radius} 米对应的网格范围为 0")
    return grid_cells


def _extract_lead_times_from_xarray(data: xr.DataArray) -> ndarray:
    """从 meb 六维 DataArray 的 dtime 坐标读取预报时效（小时）。"""
    if "dtime" not in data.coords:
        raise ValueError("xarray 输入必须包含 dtime 坐标以读取预报时效")
    coord = data.coords["dtime"]
    units = coord.attrs.get("units") or data.attrs.get("dtime_units")
    return _convert_coord_values(coord.values, units, "hours", "时效坐标")
