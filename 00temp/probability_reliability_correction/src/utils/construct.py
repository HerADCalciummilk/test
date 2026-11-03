#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Construct 方法内核：归箱、沿时间累加、堆叠可靠性表。

概率箱边界由 ``ConstructReliabilityCalibrationTables._define_probability_bins`` 定义。
"""
from __future__ import annotations

from typing import Union

import numpy as np
from numpy.ma.core import MaskedArray

SINGLE_VALUE_TOLERANCE = np.float32(1.0e-6)


def truth_invalid_mask(truth: np.ndarray) -> np.ndarray:
    """实况缺测掩码：非有限值（通常为 NaN）为 True。"""
    return ~np.isfinite(np.asarray(truth, dtype=np.float32))


def populate_reliability_bins(
    forecast: Union[MaskedArray, np.ndarray],
    truth: Union[MaskedArray, np.ndarray],
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> MaskedArray:
    """单时刻空间场归箱，返回 ``(3, n_bins, *spatial)``。"""
    forecast = np.ma.asarray(forecast)
    truth = np.ma.asarray(truth)
    probability_bins = np.asarray(probability_bins, dtype=np.float32)
    tol = np.float32(single_value_tolerance)
    bin_edges = np.concatenate(
        [
            np.array(probability_bins[:, 0]),
            np.array([probability_bins[-1, 1] + tol]),
        ]
    ).astype(probability_bins.dtype)
    bin_index = (
        np.searchsorted(bin_edges, np.ma.getdata(forecast), side="right") - 1
    )
    new_shape = (len(bin_edges),) + forecast.shape
    forecast_mask = np.broadcast_to(
        np.expand_dims(np.ma.getmaskarray(forecast), 0), new_shape
    )
    forecast_probabilities = np.zeros(new_shape, dtype=np.float32)
    np.put_along_axis(
        forecast_probabilities,
        np.expand_dims(bin_index, 0),
        np.ma.getdata(forecast).astype(np.float32),
        axis=0,
    )
    forecast_probabilities = np.ma.array(
        forecast_probabilities, mask=forecast_mask, copy=False
    )
    forecast_counts = np.zeros_like(forecast_probabilities)
    np.put_along_axis(forecast_counts, np.expand_dims(bin_index, 0), 1, axis=0)
    forecast_counts = np.ma.array(forecast_counts, mask=forecast_mask, copy=False)
    observation_counts = (
        np.expand_dims(np.isclose(np.ma.getdata(truth), 1), 0)
        & forecast_counts.astype(bool)
    ).astype(np.float32)

    reliability_table = np.ma.stack(
        [
            observation_counts[:-1, :],
            forecast_probabilities[:-1, :],
            forecast_counts[:-1, :],
        ]
    )
    return reliability_table.astype(np.float32)


def populate_masked_reliability_bins(
    forecast: np.ndarray,
    truth: np.ndarray,
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> MaskedArray:
    """实况含非有限缺测时的归箱；掩码下数据置 0。"""
    invalid = truth_invalid_mask(truth)
    forecast_ma = np.ma.masked_where(invalid, np.asarray(forecast, dtype=np.float32))
    truth_ma = np.ma.masked_where(invalid, np.asarray(truth, dtype=np.float32))
    table = populate_reliability_bins(
        forecast_ma,
        truth_ma,
        probability_bins,
        single_value_tolerance=single_value_tolerance,
    )
    table.data[np.ma.getmaskarray(table)] = 0
    return table


def add_reliability_tables(
    forecast: np.ndarray,
    truth: np.ndarray,
    threshold_reliability: MaskedArray,
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> Union[MaskedArray, np.ndarray]:
    """将新时刻表累加到已有表上（含缺测掩码按位与合并）。"""
    truth_has_invalid = np.any(truth_invalid_mask(truth))
    accum_has_mask = isinstance(
        threshold_reliability, np.ma.MaskedArray
    ) and np.any(np.ma.getmaskarray(threshold_reliability))

    if truth_has_invalid or accum_has_mask:
        if truth_has_invalid:
            table = populate_masked_reliability_bins(
                forecast,
                truth,
                probability_bins,
                single_value_tolerance=single_value_tolerance,
            )
        else:
            table = np.ma.array(
                np.ma.getdata(
                    populate_reliability_bins(
                        forecast,
                        truth,
                        probability_bins,
                        single_value_tolerance=single_value_tolerance,
                    )
                ),
                mask=False,
                dtype=np.float32,
            )
        mask = np.ma.getmaskarray(threshold_reliability) & np.ma.getmaskarray(table)
        return np.ma.array(
            np.ma.getdata(threshold_reliability) + np.ma.getdata(table),
            mask=mask,
            dtype=np.float32,
        )
    np.add(
        threshold_reliability,
        populate_reliability_bins(
            forecast,
            truth,
            probability_bins,
            single_value_tolerance=single_value_tolerance,
        ),
        out=threshold_reliability,
        dtype=np.float32,
    )
    return threshold_reliability


def accumulate_reliability_over_times(
    forecast_ltdyx: np.ndarray,
    truth_ltdyx: np.ndarray,
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> np.ndarray:
    """沿时间累加单阈值表。

    输入形状 ``(time, dtime, lat, lon)``（``dtime`` 通常为 1）。
    返回 ``(3, n_bin, lat, lon)``（缺测已填 0）。
    """
    fc = np.asarray(forecast_ltdyx, dtype=np.float32)
    tr = np.asarray(truth_ltdyx, dtype=np.float32)
    n_time = fc.shape[0]
    t0 = tr[0, 0]
    if np.any(truth_invalid_mask(t0)):
        table = populate_masked_reliability_bins(
            fc[0, 0],
            t0,
            probability_bins,
            single_value_tolerance=single_value_tolerance,
        )
    else:
        table = populate_reliability_bins(
            fc[0, 0],
            t0,
            probability_bins,
            single_value_tolerance=single_value_tolerance,
        )
    for it in range(1, n_time):
        table = add_reliability_tables(
            fc[it, 0],
            tr[it, 0],
            table,
            probability_bins,
            single_value_tolerance=single_value_tolerance,
        )
    return np.ma.filled(table, 0).astype(np.float32)


def construct_reliability_stack(
    forecast_mltdyx: np.ndarray,
    truth_mltdyx: np.ndarray,
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> np.ndarray:
    """多阈值建表。

    输入（已 squeeze member）：``(level, time, dtime, lat, lon)``。
    返回 ``(level, 3, n_bin, lat, lon)``。
    """
    fc = np.asarray(forecast_mltdyx, dtype=np.float32)
    tr = np.asarray(truth_mltdyx, dtype=np.float32)
    n_thr = fc.shape[0]
    n_bin = len(probability_bins)
    n_lat, n_lon = fc.shape[-2], fc.shape[-1]
    stacked = np.zeros((n_thr, 3, n_bin, n_lat, n_lon), dtype=np.float32)
    for ithr in range(n_thr):
        stacked[ithr] = accumulate_reliability_over_times(
            fc[ithr],
            tr[ithr],
            probability_bins,
            single_value_tolerance=single_value_tolerance,
        )
    return stacked


def construct_reliability_stack_points(
    forecast_ltx: np.ndarray,
    truth_ltx: np.ndarray,
    probability_bins: np.ndarray,
    *,
    single_value_tolerance: float = SINGLE_VALUE_TOLERANCE,
) -> np.ndarray:
    """多阈值建表（一维空间点，如站点）。

    输入 ``(level, time, n_points)``，返回 ``(level, 3, n_bin, n_points)``。
    """
    fc = np.asarray(forecast_ltx, dtype=np.float32)
    tr = np.asarray(truth_ltx, dtype=np.float32)
    # 复用网格累加：补 dtime=1、lon=1
    stacked = construct_reliability_stack(
        fc[:, :, np.newaxis, :, np.newaxis],
        tr[:, :, np.newaxis, :, np.newaxis],
        probability_bins,
        single_value_tolerance=single_value_tolerance,
    )
    return np.asarray(stacked[..., 0], dtype=np.float32)
