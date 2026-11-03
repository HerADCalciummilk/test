#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形增强模块数值辅助工具。

本模块存放自原 IMPROVER 工具模块部分迁移的梯度与邻域计算辅助函数。

约定：所有函数以下划线前缀命名，表示模块私有，不应被外部直接导入。
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve


def _regridded_adjacent_gradient(values: np.ndarray, spacing_m: float, axis: int) -> np.ndarray:
    """按原算法思路计算相邻格点梯度并线性回插到原网格。

    参数
    ----------
    values : np.ndarray
        输入二维场。
    spacing_m : float
        梯度方向的网格间距，单位为米。
    axis : int
        计算梯度的轴索引。

    返回值
    -------
    np.ndarray
        回插到原网格后的梯度场。
    """
    values = np.asarray(values, dtype=np.float64)
    diffs = np.diff(values, axis=axis) / spacing_m
    output = np.empty_like(values, dtype=np.float64)
    axis_length = values.shape[axis]
    if axis_length == 1:
        output[...] = 0.0
        return output
    if axis_length == 2:
        first = [slice(None)] * values.ndim
        second = [slice(None)] * values.ndim
        first[axis] = 0
        second[axis] = 1
        diff_index = [slice(None)] * values.ndim
        diff_index[axis] = 0
        output[tuple(first)] = diffs[tuple(diff_index)]
        output[tuple(second)] = diffs[tuple(diff_index)]
        return output
    first = [slice(None)] * values.ndim
    second = [slice(None)] * values.ndim
    interior = [slice(None)] * values.ndim
    left = [slice(None)] * values.ndim
    right = [slice(None)] * values.ndim
    diff0 = [slice(None)] * values.ndim
    diff1 = [slice(None)] * values.ndim
    difflast = [slice(None)] * values.ndim
    diffprev = [slice(None)] * values.ndim
    first[axis] = 0
    second[axis] = axis_length - 1
    interior[axis] = slice(1, axis_length - 1)
    left[axis] = slice(0, axis_length - 2)
    right[axis] = slice(1, axis_length - 1)
    diff0[axis] = 0
    diff1[axis] = 1
    difflast[axis] = -1
    diffprev[axis] = -2
    output[tuple(first)] = 1.5 * diffs[tuple(diff0)] - 0.5 * diffs[tuple(diff1)]
    output[tuple(interior)] = 0.5 * (diffs[tuple(left)] + diffs[tuple(right)])
    output[tuple(second)] = 1.5 * diffs[tuple(difflast)] - 0.5 * diffs[tuple(diffprev)]
    return output


def _square_neighbourhood_mean(values: np.ndarray, size: int) -> np.ndarray:
    """按有效邻域格点数计算方形邻域均值。

    参数
    ----------
    values : np.ndarray
        输入二维场。
    size : int
        方形邻域边长。

    返回值
    -------
    np.ndarray
        邻域均值场。
    """
    values = np.asarray(values, dtype=np.float64)
    kernel = np.ones((size, size), dtype=np.float64)
    summed = convolve(values, kernel, mode="constant", cval=0.0)
    counts = convolve(np.ones(values.shape, dtype=np.float64), kernel, mode="constant", cval=0.0)
    return summed / counts
