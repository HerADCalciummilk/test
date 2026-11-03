#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Manipulate 方法内核：欠采样并箱与观测频率单调化。"""
from __future__ import annotations

import operator
from typing import Tuple

import numpy as np


def sum_pairs(array: np.ndarray, upper: int) -> np.ndarray:
    """合并相邻箱：``upper-1`` 与 ``upper`` 求和后删除 ``upper``。"""
    result = array.copy()
    result[upper - 1] = np.sum(array[upper - 1 : upper + 1])
    return np.delete(result, upper)


def combine_bin_bounds(bounds: np.ndarray, upper: int) -> np.ndarray:
    """合并一对概率箱边界。"""
    return np.concatenate(
        (
            bounds[0 : upper - 1],
            np.array([[bounds[upper - 1, 0], bounds[upper, 1]]]),
            bounds[upper + 1 :],
        )
    ).astype(np.float32)


def combine_undersampled_bins(
    observation_count: np.ndarray,
    forecast_probability_sum: np.ndarray,
    forecast_count: np.ndarray,
    bounds: np.ndarray,
    minimum_forecast_count: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """反复合并欠采样箱，直至达标或只剩一箱。"""
    while (
        any(x < minimum_forecast_count for x in forecast_count)
        and len(forecast_count) > 1
    ):
        forecast_count_copy = forecast_count.astype(np.float64).copy()
        forecast_count_copy[forecast_count >= minimum_forecast_count] = np.nan
        index = np.int32(np.nanargmax(forecast_count_copy))
        if index == 0:
            upper = index + 1
        elif index + 1 == len(forecast_count):
            upper = index
        else:
            if forecast_count[index + 1] > forecast_count[index - 1]:
                upper = index
            else:
                upper = index + 1
        forecast_count = sum_pairs(forecast_count, upper)
        observation_count = sum_pairs(observation_count, upper)
        forecast_probability_sum = sum_pairs(forecast_probability_sum, upper)
        bounds = combine_bin_bounds(bounds, upper)
    return observation_count, forecast_probability_sum, forecast_count, bounds


def combine_bin_pair(
    observation_count: np.ndarray,
    forecast_probability_sum: np.ndarray,
    forecast_count: np.ndarray,
    bounds: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """自高概率端合并一对导致观测频率下降的邻箱。"""
    observation_frequency = np.array(observation_count / forecast_count)
    for upper in np.arange(len(observation_frequency) - 1, 0, -1):
        (diff,) = np.diff(
            [observation_frequency[upper - 1], observation_frequency[upper]]
        )
        if diff < 0:
            forecast_count = sum_pairs(forecast_count, upper)
            observation_count = sum_pairs(observation_count, upper)
            forecast_probability_sum = sum_pairs(forecast_probability_sum, upper)
            bounds = combine_bin_bounds(bounds, upper)
            break
    return observation_count, forecast_probability_sum, forecast_count, bounds


def assume_constant_observation_frequency(
    observation_count: np.ndarray, forecast_count: np.ndarray
) -> np.ndarray:
    """用常值频率修正非单调观测频率，返回新的 observation_count。"""
    observation_frequency = np.array(observation_count / forecast_count)
    iterator = observation_frequency
    op = operator.lt
    if forecast_count[0] < forecast_count[-1]:
        iterator = observation_frequency[::-1]
        op = operator.gt
    for index, lower_bin in enumerate(iterator[:-1]):
        (diff,) = np.diff([lower_bin, iterator[index + 1]])
        if op(diff, 0):
            iterator[index + 1] = lower_bin
    observation_frequency = iterator
    if forecast_count[0] < forecast_count[-1]:
        observation_frequency = iterator[::-1]
    return observation_frequency * forecast_count


def enforce_min_count_and_monotonicity(
    observation_count: np.ndarray,
    forecast_probability_sum: np.ndarray,
    forecast_count: np.ndarray,
    bounds: np.ndarray,
    minimum_forecast_count: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """欠采样合并 + 观测频率单调化。"""
    if np.any(forecast_count < minimum_forecast_count):
        (
            observation_count,
            forecast_probability_sum,
            forecast_count,
            bounds,
        ) = combine_undersampled_bins(
            observation_count,
            forecast_probability_sum,
            forecast_count,
            bounds,
            minimum_forecast_count,
        )
    observation_frequency = np.array(observation_count / forecast_count)
    if not np.all(np.diff(observation_frequency) >= 0):
        (
            observation_count,
            forecast_probability_sum,
            forecast_count,
            bounds,
        ) = combine_bin_pair(
            observation_count,
            forecast_probability_sum,
            forecast_count,
            bounds,
        )
        observation_count = assume_constant_observation_frequency(
            observation_count, forecast_count
        )
    return observation_count, forecast_probability_sum, forecast_count, bounds
