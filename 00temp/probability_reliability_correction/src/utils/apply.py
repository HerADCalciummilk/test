#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Apply 方法内核：可靠性曲线、插值订正、跨阈值单调。"""
from __future__ import annotations

import warnings
from typing import Optional, Tuple, Union

import numpy as np
import scipy
from numpy.ma.core import MaskedArray


def reliability_curve_from_counts(
    observation_count: np.ndarray,
    forecast_probability_sum: np.ndarray,
    forecast_count: np.ndarray,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """由三行计数得到 ``(平均预报概率, 观测频率)``；箱数 < 2 时返回 ``(None, None)``。"""
    obs = np.asarray(observation_count, dtype=np.float32).reshape(-1)
    psum = np.asarray(forecast_probability_sum, dtype=np.float32).reshape(-1)
    fcnt = np.asarray(forecast_count, dtype=np.float32).reshape(-1)
    if len(fcnt) < 2:
        return None, None
    return np.array(psum / fcnt), np.array(obs / fcnt)


def interpolate_probabilities(
    forecast_threshold: Union[MaskedArray, np.ndarray],
    reliability_probabilities: np.ndarray,
    observation_frequencies: np.ndarray,
) -> Union[MaskedArray, np.ndarray]:
    """用可靠性曲线对概率场做分段线性插值并 clip 到 [0, 1]。"""
    shape = forecast_threshold.shape
    mask = forecast_threshold.mask if np.ma.is_masked(forecast_threshold) else None
    forecast_probabilities = np.ma.getdata(forecast_threshold).flatten()
    interpolation_function = scipy.interpolate.interp1d(
        reliability_probabilities,
        observation_frequencies,
        fill_value="extrapolate",
    )
    y_0, y_1 = interpolation_function([0, 1])
    xp = np.copy(reliability_probabilities)
    xp[0] = 0
    xp[-1] = 1
    fp = np.copy(observation_frequencies)
    fp[0] = y_0
    fp[-1] = y_1
    interpolated = np.interp(forecast_probabilities, xp, fp)
    interpolated = interpolated.reshape(shape).astype(np.float32)
    if mask is not None:
        interpolated = np.ma.masked_array(interpolated, mask=mask)
    return np.clip(interpolated, 0, 1)


def normalize_relative_to_threshold(value: Optional[str]) -> Optional[str]:
    """将 ``relative_to_threshold`` 规范为 ``above`` / ``below``。"""
    if value in ("above", "greater_than", "greater_than_or_equal_to"):
        return "above"
    if value in ("below", "less_than", "less_than_or_equal_to"):
        return "below"
    return None


def ensure_monotonicity_across_thresholds(
    data: np.ndarray,
    relative_to_threshold: Optional[str],
    *,
    level_axis: int = 1,
) -> np.ndarray:
    """按 above/below 强制跨阈值概率单调。

    ``data`` 的 ``level_axis`` 为阈值维（网格六维中为 axis=1）；单阈值原样返回。
    """
    arr = np.asarray(data)
    if arr.shape[level_axis] <= 1:
        return arr
    if level_axis != 1:
        raise ValueError("ensure_monotonicity_across_thresholds 仅支持 level_axis=1")
    thresholding = normalize_relative_to_threshold(relative_to_threshold)
    if thresholding is None:
        raise ValueError(
            "Cube threshold coordinate does not define whether "
            "thresholding is above or below the defined thresholds."
        )
    out = np.array(arr, copy=True)
    if thresholding == "above":
        if not (np.diff(out, axis=1) <= 0).all():
            warnings.warn(
                "Exceedance probabilities are not decreasing monotonically "
                "as the threshold values increase. Forced back into order."
            )
            out = np.sort(out, axis=1)[:, ::-1, ...]
    elif thresholding == "below":
        if not (np.diff(out, axis=1) >= 0).all():
            warnings.warn(
                "Below threshold probabilities are not increasing "
                "monotonically as the threshold values increase. Forced "
                "back into order."
            )
            out = np.sort(out, axis=1)
    return out
