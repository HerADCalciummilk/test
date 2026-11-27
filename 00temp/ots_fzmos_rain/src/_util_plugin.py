# -*- coding: utf-8 -*-
"""OTS 算法辅助。阈值搜索、反距离插值、分段订正和相邻 12 小时合成。

数值关系与原程序一致。读文件和写结果不在这里。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from utils.grid import GridConfig
from utils.threshold_time import renew_day_730


# 20 个时效：012, 024, …, 240。
LEAD_HOURS = tuple((index + 1) * 12 for index in range(20))

THRESHOLD_IN = np.array(
    [0.1, 1.0, 5.0, 10.0, 25.0, 35.0, 50.0, 75.0, 100.0, 150.0],
    dtype=np.float32,
)


def build_threshold_bounds() -> np.ndarray:
    """构造每个预报时效、每个降水等级的搜索阈值上下限。"""
    threshold1 = np.zeros((20, 2, 10), dtype=np.float32)

    threshold1[0, 0, :] = [0.1, 0.5, 2.5, 8.0, 17.0, 25.0, 35.0, 48.0, 66.0, 81.0]
    threshold1[0, 1, :] = [3.0, 4.0, 7.5, 12.0, 25.0, 35.0, 47.0, 65.0, 80.0, 110.0]
    threshold1[4, 0, :] = [0.1, 0.5, 2.5, 8.0, 17.0, 28.0, 38.0, 48.0, 70.0, 85.0]
    threshold1[4, 1, :] = [3.0, 4.0, 7.5, 12.0, 25.0, 35.0, 47.0, 65.0, 85.0, 115.0]
    threshold1[8, 0, :] = [0.1, 0.5, 2.5, 8.0, 17.0, 28.0, 38.0, 50.0, 70.0, 85.0]
    threshold1[8, 1, :] = [3.0, 4.0, 7.5, 12.0, 25.0, 35.0, 47.0, 65.0, 85.0, 115.0]

    threshold1[1:4, :, :] = threshold1[0, :, :]
    threshold1[5:8, :, :] = threshold1[4, :, :]
    threshold1[9:20, :, :] = threshold1[8, :, :]
    return threshold1


def _score_one_pair(
    forecast_values: np.ndarray,
    observed_values: np.ndarray,
    candidate_thresholds: np.ndarray,
    threshold_in: np.ndarray,
    hits: np.ndarray,
    false_alarms: np.ndarray,
    misses: np.ndarray,
    correct_negatives: np.ndarray,
) -> None:
    """统计一组预报和实况在 30 个候选阈值下的命中、空报、漏报和正确否定次数。"""
    # Fortran 原程序使用默认 REAL（float32），有效性和阈值比较都基于单精度值。
    forecast_values = np.asarray(forecast_values, dtype=np.float32)
    observed_values = np.asarray(observed_values, dtype=np.float32)
    valid = (forecast_values < 600.0) & (observed_values < 600.0)
    if not np.any(valid):
        return

    forecast = forecast_values[valid]
    observed = observed_values[valid]

    forecast_event = forecast[:, None, None] >= candidate_thresholds[None, :, :]
    observed_event = observed[:, None] >= threshold_in[None, :]
    observed_event = observed_event[:, None, :]

    hits += np.count_nonzero(forecast_event & observed_event, axis=0)
    false_alarms += np.count_nonzero(forecast_event & ~observed_event, axis=0)
    misses += np.count_nonzero(~forecast_event & observed_event, axis=0)
    correct_negatives += np.count_nonzero(~forecast_event & ~observed_event, axis=0)


def calculate_lead_threshold(
    fh_index: int,
    iday: int,
    start_day: int,
    station_count: int,
    ec_by_year: dict[int, np.ndarray],
    obs_by_year: dict[int, np.ndarray],
    threshold_in: np.ndarray = THRESHOLD_IN,
    begin_year: int | None = None,
    end_year: int | None = None,
) -> np.ndarray:
    """计算一个预报时效上 10 个降水等级的最佳映射阈值。评分公式与原循环体相同。"""
    if end_year is None:
        end_year = max(obs_by_year)
    if begin_year is None:
        begin_year = end_year - 2

    threshold_in = np.asarray(threshold_in, dtype=np.float32)
    threshold_bounds = build_threshold_bounds()
    low = threshold_bounds[fh_index, 0, :]
    high = threshold_bounds[fh_index, 1, :]
    candidate_thresholds = low[None, :] + (high - low)[None, :] * (
        np.arange(30, dtype=np.float32)[:, None] / np.float32(29.0)
    )

    hits = np.zeros((30, 10), dtype=np.int64)
    false_alarms = np.zeros((30, 10), dtype=np.int64)
    misses = np.zeros((30, 10), dtype=np.int64)
    correct_negatives = np.zeros((30, 10), dtype=np.int64)

    for ii in range(1, iday * 2 + 1):
        for year in range(begin_year, end_year + 1):
            sk_day = start_day + ii - iday * 2 - 2
            yb_day = sk_day - fh_index
            yb_year, yb_day = renew_day_730(year, yb_day)
            sk_year, sk_day = renew_day_730(year, sk_day)

            _score_one_pair(
                ec_by_year[yb_year][fh_index, yb_day - 1, :station_count],
                obs_by_year[sk_year][sk_day - 1, :station_count],
                candidate_thresholds,
                threshold_in,
                hits,
                false_alarms,
                misses,
                correct_negatives,
            )

            yb_day = start_day + ii - 2
            sk_day = yb_day + fh_index
            yb_year, yb_day = renew_day_730(year - 1, yb_day)
            sk_year, sk_day = renew_day_730(year - 1, sk_day)

            _score_one_pair(
                ec_by_year[yb_year][fh_index, yb_day - 1, :station_count],
                obs_by_year[sk_year][sk_day - 1, :station_count],
                candidate_thresholds,
                threshold_in,
                hits,
                false_alarms,
                misses,
                correct_negatives,
            )

    denominator = hits + misses + false_alarms
    with np.errstate(divide="ignore", invalid="ignore"):
        ts = hits.astype(np.float32) / denominator.astype(np.float32)

    row = np.empty(10, dtype=np.float32)
    for threshold_index in range(10):
        optimal = 0
        for candidate_index in range(1, 30):
            if ts[optimal, threshold_index] < ts[candidate_index, threshold_index]:
                optimal = candidate_index
        row[threshold_index] = (
            low[threshold_index]
            + (high[threshold_index] - low[threshold_index]) * optimal / 29.0
        )
    return row


def calculate_thresholds(
    iday: int,
    start_day: int,
    station_count: int,
    ec_by_year: dict[int, np.ndarray],
    obs_by_year: dict[int, np.ndarray],
    threshold_in: np.ndarray = THRESHOLD_IN,
    begin_year: int | None = None,
    end_year: int | None = None,
) -> np.ndarray:
    """计算各预报时效和降水等级的最佳映射阈值。"""
    threshold_out = np.empty((20, 10), dtype=np.float32)
    for fh_index in range(20):
        threshold_out[fh_index, :] = calculate_lead_threshold(
            fh_index,
            iday,
            start_day,
            station_count,
            ec_by_year,
            obs_by_year,
            threshold_in=threshold_in,
            begin_year=begin_year,
            end_year=end_year,
        )
    return threshold_out


@dataclass(frozen=True)
class InterpolationPlan:
    """保存规则网格插值中可重复使用的坐标和索引。"""

    source: GridConfig
    target: GridConfig
    radius: np.float32
    base_x: np.ndarray
    base_y: np.ndarray
    target_lons: np.ndarray
    target_lats: np.ndarray
    offset_x: int
    offset_y: int
    reverse_source_rows: bool


def _normalize_source_latitude(source: GridConfig) -> tuple[GridConfig, bool]:
    """将递增纬度网格转换为原Fortran程序使用的递减顺序。"""
    if source.dlat < 0.0:
        return source, False

    normalized = GridConfig(
        lat_start=source.lat_end,
        lon_start=source.lon_start,
        lat_end=source.lat_start,
        lon_end=source.lon_end,
        dlat=-source.dlat,
        dlon=source.dlon,
        num_x=source.num_x,
        num_y=source.num_y,
    )
    return normalized, True


def build_interpolation_plan(
    source: GridConfig,
    target: GridConfig,
    radius: float = 0.7,
) -> InterpolationPlan:
    """预先计算目标格点坐标、最近源格点及搜索范围。"""
    normalized_source, reverse_source_rows = _normalize_source_latitude(source)
    source = normalized_source
    source_dlon = np.float32(source.dlon)
    source_dlat = np.float32(source.dlat)
    target_lons = np.float32(target.lon_start) + np.arange(
        target.num_x, dtype=np.float32
    ) * np.float32(target.dlon)
    target_lats = np.float32(target.lat_start) + np.arange(
        target.num_y, dtype=np.float32
    ) * np.float32(target.dlat)

    base_x = np.trunc(
        (target_lons - np.float32(source.lon_start)) / source_dlon
    ).astype(np.int32)
    base_y = np.trunc(
        (target_lats - np.float32(source.lat_start)) / source_dlat
    ).astype(np.int32)
    radius32 = np.float32(radius)

    return InterpolationPlan(
        source=source,
        target=target,
        radius=radius32,
        base_x=base_x,
        base_y=base_y,
        target_lons=target_lons,
        target_lats=target_lats,
        offset_x=int(abs(radius32 / source_dlon)),
        offset_y=int(abs(radius32 / source_dlat)),
        reverse_source_rows=reverse_source_rows,
    )


def inverse_distance_interpolate(
    data_in: np.ndarray,
    plan: InterpolationPlan,
) -> np.ndarray:
    """复现原程序半径内反距离权重插值，缺测值使用9999。"""
    source_values = np.asarray(data_in, dtype=np.float32)
    expected_shape = (plan.source.num_y, plan.source.num_x)
    if source_values.shape != expected_shape:
        raise ValueError(f"输入网格形状为 {source_values.shape}，预期为 {expected_shape}")
    if plan.reverse_source_rows:
        source_values = source_values[::-1].copy()

    target_shape = (plan.target.num_y, plan.target.num_x)
    if not np.any(source_values < np.float32(2000.0)):
        return np.full(target_shape, np.float32(9999.0), dtype=np.float32)

    weighted_sum = np.zeros(target_shape, dtype=np.float32)
    weight_sum = np.zeros(target_shape, dtype=np.float32)
    radius_squared = np.float32(plan.radius * plan.radius)
    source_lon = np.float32(plan.source.lon_start)
    source_lat = np.float32(plan.source.lat_start)
    source_dlon = np.float32(plan.source.dlon)
    source_dlat = np.float32(plan.source.dlat)

    # 循环顺序保持与 Fortran 的 k1、k0 顺序一致，以减少浮点累加差异。
    for offset_y in range(-plan.offset_y, plan.offset_y + 1):
        rows = plan.base_y + offset_y
        row_valid = (rows >= 0) & (rows < plan.source.num_y)
        safe_rows = np.clip(rows, 0, plan.source.num_y - 1)
        source_lats = source_lat + rows.astype(np.float32) * source_dlat
        lat_distance = (source_lats - plan.target_lats) ** np.float32(2.0)

        for offset_x in range(-plan.offset_x, plan.offset_x + 1):
            columns = plan.base_x + offset_x
            column_valid = (columns >= 0) & (columns < plan.source.num_x)
            safe_columns = np.clip(columns, 0, plan.source.num_x - 1)
            source_lons = source_lon + columns.astype(np.float32) * source_dlon
            lon_distance = (source_lons - plan.target_lons) ** np.float32(2.0)

            distance_squared = lat_distance[:, None] + lon_distance[None, :]
            weights = (radius_squared - distance_squared) / (
                radius_squared + distance_squared
            )
            values = source_values[np.ix_(safe_rows, safe_columns)]
            usable = (
                row_valid[:, None]
                & column_valid[None, :]
                & (values < np.float32(2000.0))
                & (weights > np.float32(0.0))
            )

            contribution = weights * values
            weighted_sum[usable] += contribution[usable]
            weight_sum[usable] += weights[usable]

    result = np.full(target_shape, np.float32(9999.0), dtype=np.float32)
    usable_output = weight_sum > np.float32(0.0)
    result[usable_output] = weighted_sum[usable_output] / weight_sum[usable_output]
    return result


def correct_precipitation(
    values: np.ndarray,
    threshold_out: np.ndarray,
    threshold_in: np.ndarray = THRESHOLD_IN,
) -> np.ndarray:
    """按照原程序的分段线性关系对一个格点场进行 OTS 降水订正。"""
    source = np.asarray(values, dtype=np.float32)
    mapped = np.full(source.shape, np.float32(9999.0), dtype=np.float32)
    valid = source < np.float32(2000.0)
    if not np.any(valid):
        return mapped

    source_valid = source[valid]
    output_valid = np.zeros(source_valid.shape, dtype=np.float32)
    thresholds = np.asarray(threshold_out, dtype=np.float32)
    targets = np.asarray(threshold_in, dtype=np.float32)

    for index in range(9):
        selected = (source_valid >= thresholds[index]) & (
            source_valid < thresholds[index + 1]
        )
        if not np.any(selected):
            continue
        output_valid[selected] = targets[index] + (
            (source_valid[selected] - thresholds[index])
            * (targets[index + 1] - targets[index])
            / (thresholds[index + 1] - thresholds[index])
        )

    upper = source_valid >= thresholds[-1]
    if np.any(upper):
        output_valid[upper] = targets[-1] / thresholds[-1] * source_valid[upper]

    output_valid[output_valid > np.float32(2000.0)] = np.float32(9999.0)
    mapped[valid] = output_valid
    return mapped


def combine_rain24(current, previous):
    """相邻两个已订正的 12 小时场相加。超过 2000 的格点记为缺测。"""
    rain24 = current + previous
    rain24[rain24 > np.float32(2000.0)] = np.float32(9999.0)
    return rain24
