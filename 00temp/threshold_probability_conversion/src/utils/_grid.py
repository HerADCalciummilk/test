#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Threshold vicinity 用网格间距推断（米制等距投影）。"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import xarray as xr
from cf_units import Unit


def _coord_values_in_metres(values: np.ndarray, unit: str | None) -> np.ndarray:
    """将一维坐标换算为米。"""
    arr = np.asarray(values, dtype=np.float64)
    if unit is None or str(unit).strip() == "":
        raise ValueError("空间坐标缺少 units，无法按米制推断格距。")
    return Unit(str(unit).strip()).convert(arr, Unit("m"))


def infer_equal_area_grid_spacing_m(data: xr.DataArray) -> float:
    """从 ``lat/lon`` 维推断等距投影网格间距（米）。

    调用方须保证空间轴已为米制：投影 meb（坐标 ``units`` 为距离）或
    经纬经 LAEA 适配后的 DataArray。与 IMPROVER 一致：要求 x/y 等间距且相等。
    """
    if data.ndim < 2:
        raise ValueError("推断网格间距至少需要二维空间场。")
    y_name, x_name = data.dims[-2], data.dims[-1]
    y = data.coords[y_name].values
    x = data.coords[x_name].values
    if y.size < 2 or x.size < 2:
        raise ValueError("空间坐标长度不足，无法计算网格间距。")

    y_m = _coord_values_in_metres(y, data.coords[y_name].attrs.get("units"))
    x_m = _coord_values_in_metres(x, data.coords[x_name].attrs.get("units"))
    y_diff = np.abs(np.diff(y_m))
    x_diff = np.abs(np.diff(x_m))
    y_spacing = float(np.mean(y_diff))
    x_spacing = float(np.mean(x_diff))
    if not np.allclose(y_diff, y_spacing, rtol=1.0e-5, atol=0.0):
        raise ValueError(f"{y_name} 坐标不是等间距网格。")
    if not np.allclose(x_diff, x_spacing, rtol=1.0e-5, atol=0.0):
        raise ValueError(f"{x_name} 坐标不是等间距网格。")
    if not np.isclose(y_spacing, x_spacing, rtol=1.0e-5, atol=0.0):
        raise ValueError("x 和 y 方向的网格间距必须一致（等面积投影）。")
    return y_spacing


def distance_to_number_of_grid_cells(distance_m: float, grid_spacing_m: float) -> int:
    """米制半径 → 格点半径（向下取整，与 IMPROVER 一致）。"""
    if distance_m <= 0:
        raise ValueError(f"邻域半径须为正数（米），当前为 {distance_m}")
    if grid_spacing_m <= 0:
        raise ValueError(f"网格间距须为正数（米），当前为 {grid_spacing_m}")
    grid_cells = int(distance_m / abs(grid_spacing_m))
    if grid_cells == 0:
        raise ValueError(f"半径 {distance_m} 米在该网格上对应 0 个格点。")
    return grid_cells
