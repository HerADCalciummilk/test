#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""邻域内现象出现（vicinity）与阈值辅助，供 AdjustLandSeaPoints 使用。"""

from __future__ import annotations

import numpy as np
from numpy import ndarray
from scipy.ndimage import maximum_filter


def apply_threshold(
    data: ndarray, threshold_value: float = 0.5, comparison_operator: str = ">"
) -> ndarray:
    """对二维场做二值阈值，返回 float32 的 0/1 场。"""
    arr = np.asarray(data)
    if comparison_operator in (">", "gt"):
        result = arr > threshold_value
    elif comparison_operator in (">=", "ge"):
        result = arr >= threshold_value
    elif comparison_operator in ("<", "lt"):
        result = arr < threshold_value
    elif comparison_operator in ("<=", "le"):
        result = arr <= threshold_value
    else:
        raise ValueError(f"Unsupported comparison_operator: {comparison_operator}")
    return result.astype(np.float32)


def maximum_within_vicinity(grid: ndarray, grid_point_radius: int) -> ndarray:
    """在方形邻域内取最大值，等价于原算法 vicinity max 的核心行为。"""
    width = 2 * int(grid_point_radius) + 1
    data = np.asarray(grid, dtype=np.float32)
    if np.any(np.isnan(data)):
        filled = np.where(np.isnan(data), -np.inf, data)
        out = maximum_filter(filled, size=width, mode="nearest")
        return np.where(np.isneginf(out), np.nan, out).astype(np.float32)
    return maximum_filter(data, size=width, mode="nearest").astype(np.float32)
