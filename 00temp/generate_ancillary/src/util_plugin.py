# -*- coding: utf-8 -*-
"""地形辅助场的计算步骤。掩码拼网格仍由 ``src/utils`` 提供，这里再导出。"""
from __future__ import annotations

from typing import Sequence

import numpy as np
from numpy import ndarray

from generate_ancillary.src.utils._make_mask_griddata import make_mask_griddata  # noqa: F401


def band_weights(points: ndarray, band: Sequence[float]) -> ndarray:
    """带中点权重 1，上下界权重 0.5，中间线性插值。"""
    weights = np.array([0.5, 1.0, 0.5], np.float32)
    midpoint = np.mean(band)
    band_points = np.array([band[0], midpoint, band[1]], np.float32)
    return np.interp(points, band_points, weights).astype(np.float32)
