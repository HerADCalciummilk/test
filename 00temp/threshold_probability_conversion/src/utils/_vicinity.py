#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""邻域内最大值（vicinity）辅助，供 Threshold 使用。

逻辑迁移自 IMPROVER ``improver.utilities.spatial`` 的
``operator_within_vicinity`` / ``maximum_within_vicinity``。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Union

import numpy as np
from numpy import ndarray
from numpy.ma.core import MaskedArray
from scipy.ndimage import maximum_filter

FLOAT_DTYPE = np.float32


def _operator_within_vicinity(
    apply_filter: Callable[[ndarray, int], ndarray],
    fill_value: float,
    grid: Union[MaskedArray, ndarray],
    grid_point_radius: int,
    landmask: Optional[ndarray] = None,
) -> Union[MaskedArray, ndarray]:
    """在方形邻域内对二维场施加滤波；可选海陆掩码分别处理。"""
    grid_points = (2 * int(grid_point_radius)) + 1
    processed_grid = grid.copy()
    if np.ma.is_masked(grid):
        unmasked_grid = grid.data.copy()
        unmasked_grid[grid.mask] = fill_value
    else:
        unmasked_grid = np.asarray(grid).copy()

    if landmask is not None:
        patch_data = np.empty_like(unmasked_grid)
        for match in (True, False):
            matched_data = unmasked_grid.copy()
            matched_data[landmask != match] = fill_value
            matched_patch_data = apply_filter(matched_data, grid_points)
            patch_data = np.where(landmask == match, matched_patch_data, patch_data)
    else:
        patch_data = apply_filter(unmasked_grid, grid_points)

    if np.ma.is_masked(grid):
        processed_grid.data[~grid.mask] = patch_data[~grid.mask]
    else:
        processed_grid = patch_data
    return processed_grid


def _apply_max_filter(data: ndarray, width: int) -> ndarray:
    """方形窗口最大值；NaN 用 -inf 填充后滤波再恢复。"""
    if np.any(np.isnan(data)):
        filled = np.where(np.isnan(data), -np.inf, data)
        out = maximum_filter(filled, size=width, mode="nearest")
        return np.where(np.isneginf(out), np.nan, out).astype(FLOAT_DTYPE)
    return maximum_filter(data, size=width, mode="nearest").astype(FLOAT_DTYPE)


def maximum_within_vicinity(
    grid: Union[MaskedArray, ndarray],
    grid_point_radius: int,
    landmask: Optional[ndarray] = None,
) -> Union[MaskedArray, ndarray]:
    """在指定格点半径的方形邻域内取最大值。"""
    fill_value = -np.inf
    return _operator_within_vicinity(
        _apply_max_filter,
        fill_value,
        grid,
        grid_point_radius,
        landmask,
    )


def apply_vicinity_to_slices(
    truths: ndarray,
    grid_point_radii: list[int],
    landmask: Optional[ndarray] = None,
) -> Union[ndarray, List[ndarray]]:
    """对 ``(..., lat, lon)`` 真值场沿最后两维做 vicinity max。

    Parameters
    ----------
    truths :
        形状 ``(..., n_lat, n_lon)``。
    grid_point_radii :
        邻域半径（格点数）。
    landmask :
        与 ``lat/lon`` 同形的 bool 海陆掩码；``True`` 为陆。

    Returns
    -------
    ndarray or list[ndarray]
        单半径时与输入同形；多半径时返回各半径对应的六维数组列表。
    """
    spatial_shape = truths.shape[-2:]
    if landmask is not None:
        landmask = np.asarray(landmask, dtype=bool)
        if landmask.shape != spatial_shape:
            raise ValueError(
                f"landmask 空间形状须与输入一致，"
                f"landmask={landmask.shape}, data={spatial_shape}"
            )

    prefix_shape = truths.shape[:-2]
    n_slices = int(np.prod(prefix_shape)) if prefix_shape else 1
    flat = truths.reshape(n_slices, *spatial_shape)

    if len(grid_point_radii) == 1:
        radius = grid_point_radii[0]
        out = np.empty_like(flat, dtype=FLOAT_DTYPE)
        for i in range(n_slices):
            out[i] = maximum_within_vicinity(flat[i], radius, landmask)
        return out.reshape(truths.shape)

    outputs = []
    for radius in grid_point_radii:
        layer = np.empty_like(flat, dtype=FLOAT_DTYPE)
        for i in range(n_slices):
            layer[i] = maximum_within_vicinity(flat[i], radius, landmask)
        outputs.append(layer.reshape(truths.shape))
    return outputs
