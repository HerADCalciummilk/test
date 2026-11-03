#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""邻域卷积与方形窗口求和工具（对应 IMPROVER neighbourhood_tools）。"""

from __future__ import annotations

from typing import Any, Tuple, Union

import numpy as np
from numpy import ndarray


def _rolling_window(
    input_array: ndarray, shape: Tuple[int, int], writeable: bool = False
) -> ndarray:
    """在最后两个维度上构造滚动窗口视图。"""
    num_window_dims = len(shape)
    num_arr_dims = len(input_array.shape)
    if num_arr_dims < num_window_dims:
        raise ValueError("输入数组维度少于窗口维度")
    out_shape = (
        *input_array.shape[:-num_window_dims],
        *(
            arr_dim - win_dim + 1
            for arr_dim, win_dim in zip(input_array.shape[-num_window_dims:], shape)
        ),
        *shape,
    )
    if any(dim <= 0 for dim in out_shape):
        raise RuntimeError("窗口尺寸大于输入数组尺寸")
    strides = input_array.strides + input_array.strides[-num_window_dims:]
    return np.lib.stride_tricks.as_strided(
        input_array, shape=out_shape, strides=strides, writeable=writeable
    )


def _pad_and_roll(
    input_array: ndarray, shape: Tuple[int, int], **kwargs: Any
) -> ndarray:
    """先 pad 再构造滚动窗口。"""
    writeable = kwargs.pop("writeable", False)
    pad_extent = [(0, 0)] * (input_array.ndim - len(shape))
    pad_extent.extend((dim // 2, dim // 2) for dim in shape)
    padded = np.pad(input_array, pad_extent, **kwargs)
    return _rolling_window(padded, shape, writeable=writeable)


def _pad_boxsum(
    data: ndarray, boxsize: Union[int, Tuple[int, int]], **pad_options: Any
) -> ndarray:
    """为 boxsum 生成所需 padding。"""
    boxsize = np.atleast_1d(boxsize)
    ih, jh = boxsize[0] // 2, boxsize[-1] // 2
    padding = [(0, 0)] * (data.ndim - 2) + [(ih + 1, ih), (jh + 1, jh)]
    return np.pad(data, padding, **pad_options)


def _boxsum(
    data: ndarray,
    boxsize: Union[int, Tuple[int, int]],
    cumsum: bool = True,
    **pad_options: Any,
) -> ndarray:
    """快速计算方形邻域内求和。"""
    boxsize = np.atleast_1d(boxsize)
    if not issubclass(boxsize.dtype.type, np.integer):
        raise ValueError("邻域尺寸必须是整数")
    if not np.all(boxsize % 2):
        raise ValueError("邻域尺寸必须为奇数")
    if pad_options:
        data = _pad_boxsum(data, boxsize, **pad_options)
    if cumsum:
        data = data.cumsum(-2).cumsum(-1)
    i, j = boxsize[0], boxsize[-1]
    m, n = data.shape[-2] - i, data.shape[-1] - j
    return (
        data[..., i : i + m, j : j + n]
        - data[..., :m, j : j + n]
        + data[..., :m, :n]
        - data[..., i : i + m, :n]
    )
