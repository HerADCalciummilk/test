#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""相邻格点梯度。

对应原 Improver ``GradientBetweenAdjacentGridSquares(regrid=False)``：
- 投影/距离坐标：格距转米后差分；
- 经纬度（度）：正球体球面格距（对齐 ``LatLonCubeDistanceCalculator``）。
"""

from __future__ import annotations

import numpy as np
from cf_units import Unit

# 业务经纬网格无地球半径元数据；与 Iris GeogCS / Improver 常用默认一致
DEFAULT_SPHERE_RADIUS_M = 6371229.0


def _axis_values_to_meters(
    values: np.ndarray, units: str | None, axis_name: str
) -> np.ndarray:
    """将投影/距离坐标轴数值转换到米。"""
    values = np.asarray(values, dtype=np.float64)
    if units is None or not str(units).strip():
        raise ValueError(
            f"{axis_name} 缺少可转换为米的 units；"
            "若为经纬度输入，请省略 units 或使用 degrees。"
        )
    unit_text = str(units).strip()
    try:
        return Unit(unit_text).convert(values, Unit("m"))
    except Exception as err:
        raise ValueError(
            f"{axis_name} 坐标单位 {unit_text!r} 无法转换为米。"
        ) from err


def _uniform_spacing_meters(coord_m: np.ndarray, axis_name: str) -> float:
    """校验等间距并返回平均格距（米，正值）。"""
    diffs = np.abs(np.diff(np.asarray(coord_m, dtype=np.float64)))
    if diffs.size < 1:
        raise ValueError(f"{axis_name} 坐标长度不足，无法计算格距。")
    spacing = float(np.mean(diffs))
    if not np.allclose(diffs, spacing, rtol=1.0e-5, atol=0.0):
        raise ValueError(f"{axis_name} 坐标点非等间距，无法按投影路径计算格距。")
    return spacing


def _is_latlon_units(units: str | None) -> bool:
    """判断坐标单位是否为经纬度（度）。

    约定：无 units / 空字符串视为经纬输入（业务经纬网格常不带单位属性）。
    """
    if units is None or not str(units).strip():
        return True
    unit_text = str(units).strip().lower()
    return unit_text in (
        "degrees",
        "degree",
        "deg",
        "°",
        "degrees_north",
        "degrees_east",
    )


def adjacent_gradients_projected(
    values_2d: np.ndarray,
    lat_values: np.ndarray,
    lon_values: np.ndarray,
    *,
    lat_units: str | None,
    lon_units: str | None,
    sphere_radius: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """计算网格上的 x/y 相邻梯度。

    约定输入二维场顺序为 ``(lat, lon)``。

    坐标类型检测逻辑：
    - lat/lon 的 units 均为空或为度 → 经纬球面路径；
    - units 可转换为米 → 投影路径；
    - 否则抛出异常。

    经纬路径使用正球体半径 ``sphere_radius``（默认 ``DEFAULT_SPHERE_RADIUS_M``）。
    业务经纬场通常无 ``grid_mapping_attrs``，不从该属性读半径。

    返回
    ------
    grad_x : ndarray, shape (ny, nx-1)
    grad_y : ndarray, shape (ny-1, nx)
    lon_mid_x : ndarray
    lat_mid_y : ndarray
    """
    values_2d = np.asarray(values_2d, dtype=np.float64)
    if values_2d.ndim != 2:
        raise ValueError(f"期望二维场，收到 shape={values_2d.shape}")

    lat_values = np.asarray(lat_values, dtype=np.float64)
    lon_values = np.asarray(lon_values, dtype=np.float64)
    if values_2d.shape != (lat_values.size, lon_values.size):
        raise ValueError(
            f"二维场形状 {values_2d.shape} 与坐标长度 "
            f"(lat={lat_values.size}, lon={lon_values.size}) 不一致。"
        )

    is_latlon = _is_latlon_units(lat_units) and _is_latlon_units(lon_units)
    if is_latlon:
        radius = (
            DEFAULT_SPHERE_RADIUS_M
            if sphere_radius is None
            else float(sphere_radius)
        )
        return _gradients_latlon(
            values_2d, lat_values, lon_values, sphere_radius=radius
        )
    return _gradients_projected(
        values_2d, lat_values, lon_values, lat_units, lon_units
    )


def _gradients_latlon(
    values_2d: np.ndarray,
    lat_values: np.ndarray,
    lon_values: np.ndarray,
    *,
    sphere_radius: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """经纬度输入：正球体模型，逐段 diff 计算格距（对齐 LatLonCubeDistanceCalculator）。"""
    # 有符号经/纬差，保留坐标递减时的距离符号（与 Improver 一致）
    lon_diffs = np.diff(lon_values)  # (nx-1,)
    lat_diffs = np.diff(lat_values)  # (ny-1,)

    # dx[j, i] = R * cos(lat[j]) * dlon[i]（弧度）
    lats_as_col = np.expand_dims(lat_values, axis=1)
    dx = sphere_radius * np.cos(np.deg2rad(lats_as_col)) * np.deg2rad(lon_diffs)

    # dy 仅随纬度间隔变化，再广播到全部经度
    dy = sphere_radius * np.deg2rad(lat_diffs)
    dy_grid = np.broadcast_to(dy[:, None], (lat_values.size - 1, lon_values.size))

    grad_x = (np.diff(values_2d, axis=1) / dx).astype(np.float32)
    grad_y = (np.diff(values_2d, axis=0) / dy_grid).astype(np.float32)

    lon_mid_x = (0.5 * (lon_values[1:] + lon_values[:-1])).astype(np.float32)
    lat_mid_y = (0.5 * (lat_values[1:] + lat_values[:-1])).astype(np.float32)
    return grad_x, grad_y, lon_mid_x, lat_mid_y


def _gradients_projected(
    values_2d: np.ndarray,
    lat_values: np.ndarray,
    lon_values: np.ndarray,
    lat_units: str | None,
    lon_units: str | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """投影输入：坐标转米后算格距；中点坐标仍保持输入原单位。"""
    lat_m = _axis_values_to_meters(lat_values, lat_units, "lat")
    lon_m = _axis_values_to_meters(lon_values, lon_units, "lon")

    # 格距必须用米；中点坐标返回原始单位，与 Improver 一致
    dx = _uniform_spacing_meters(lon_m, "lon")
    dy = _uniform_spacing_meters(lat_m, "lat")

    diff_x = np.diff(values_2d, axis=1)
    diff_y = np.diff(values_2d, axis=0)
    grad_x = (diff_x / dx).astype(np.float32)
    grad_y = (diff_y / dy).astype(np.float32)

    lon_mid_x = (0.5 * (lon_values[1:] + lon_values[:-1])).astype(np.float32)
    lat_mid_y = (0.5 * (lat_values[1:] + lat_values[:-1])).astype(np.float32)
    return grad_x, grad_y, lon_mid_x, lat_mid_y
