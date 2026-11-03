#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""线性重标定工具（迁移自 improver.utilities.rescale）。"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union

import numpy as np
from numpy import ndarray


def rescale(
    data: ndarray,
    data_range: Optional[Union[Tuple[float, float], List[float]]] = None,
    scale_range: Union[Tuple[float, float], List[float]] = (0.0, 1.0),
    clip: bool = False,
) -> ndarray:
    """将数据从 ``data_range`` 线性映射到 ``scale_range``。

    Parameters
    ----------
    data :
        源数组。
    data_range :
        源区间 ``[min, max]``；默认取 ``data`` 的最小/最大。
    scale_range :
        目标区间，默认 ``(0, 1)``。
    clip :
        为 True 时将结果裁剪到 ``scale_range`` 两端。
    """
    data_left = np.min(data) if data_range is None else data_range[0]
    data_right = np.max(data) if data_range is None else data_range[1]
    scale_left = scale_range[0]
    scale_right = scale_range[1]
    if data_left == data_right:
        raise ValueError(
            "Cannot rescale a zero input range ({} -> {})".format(
                data_left, data_right
            )
        )
    if scale_left == scale_right:
        raise ValueError(
            "Cannot rescale a zero output range ({} -> {})".format(
                scale_left, scale_right
            )
        )

    result = (
        (data - data_left) * (scale_right - scale_left) / (data_right - data_left)
    ) + scale_left
    if clip:
        result = np.clip(
            result, min(scale_left, scale_right), max(scale_left, scale_right)
        )
    return result
