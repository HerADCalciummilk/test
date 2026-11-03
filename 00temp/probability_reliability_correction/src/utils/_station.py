#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""站点路径：meb ``DataFrame`` 编排与可靠性长表辅助。

数值核心在 ``construct`` / ``manipulate`` / ``apply``；
本模块负责六列站点表对齐、长表组装与校验。
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd

from probability_reliability_correction.src.utils._reliability import TABLE_ROW_NAMES

try:
    from meteva_base.basicdata.sta_data import sta_data as meb_sta_data
except ImportError:  # pragma: no cover
    meb_sta_data = None

# meb 站点表固定列：预报 time=起报；实况 time=有效时间、dtime 通常为 0
STA_REQUIRED_COLUMNS: Tuple[str, ...] = (
    "level",
    "time",
    "dtime",
    "id",
    "lon",
    "lat",
)

RELIABILITY_LONG_COLUMNS: Tuple[str, ...] = (
    "level",
    "time",
    "dtime",
    "id",
    "lon",
    "lat",
    "bin_index",
    "probability_bin",
    "probability_bin_bound_lower",
    "probability_bin_bound_upper",
    *TABLE_ROW_NAMES,
)

AGGREGATED_STATION_ID = np.int32(-1)
SPATIAL_KIND_STATION = "station"
SPATIAL_KIND_AGGREGATED = "aggregated"


def ensure_sta_data(df: pd.DataFrame) -> pd.DataFrame:
    """规范为 meb 站点表（有 meb 则走 ``sta_data``）。"""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"站点输入须为 pandas.DataFrame，收到 {type(df)}")
    if meb_sta_data is not None:
        out = meb_sta_data(df.copy())
    else:  # pragma: no cover
        out = df.copy()
    require_columns(out, STA_REQUIRED_COLUMNS)
    out["level"] = out["level"].astype(np.float32)
    out["time"] = pd.to_datetime(out["time"])
    out["dtime"] = out["dtime"].astype(np.float32)
    out["id"] = out["id"].astype(np.int32)
    out["lon"] = out["lon"].astype(np.float32)
    out["lat"] = out["lat"].astype(np.float32)
    # 保留调用方 attrs（sta_data 可能丢掉）
    if getattr(df, "attrs", None):
        out.attrs = dict(df.attrs)
    return out


def require_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"站点表缺少列: {missing}")


def value_column(df: pd.DataFrame, data_name: Optional[str] = None) -> str:
    """解析概率/事件要素列名。"""
    if data_name is not None:
        if data_name not in df.columns:
            raise ValueError(f"要素列 {data_name!r} 不存在")
        return data_name
    extras = [c for c in df.columns if c not in STA_REQUIRED_COLUMNS]
    if len(extras) != 1:
        raise ValueError(
            "无法自动判定要素列；请指定 data_name。"
            f" 当前非六列列名: {extras}"
        )
    return extras[0]


def add_valid_time(df: pd.DataFrame) -> pd.DataFrame:
    """增加 ``valid_time = time + dtime``（小时）。"""
    out = df.copy()
    out["valid_time"] = out["time"] + pd.to_timedelta(
        out["dtime"].astype(np.float64), unit="h"
    )
    return out


def check_forecast_consistency_sta(forecast: pd.DataFrame) -> None:
    """检查预报 FRT 钟点唯一且 ``dtime`` 唯一。"""
    hours = {int(pd.Timestamp(t).hour) for t in forecast["time"]}
    if len(hours) != 1:
        raise ValueError(
            "Forecasts have been provided with differing hours for the "
            f"forecast reference time {hours}"
        )
    dtimes = np.unique(np.asarray(forecast["dtime"].values, dtype=np.float32))
    if dtimes.size != 1:
        raise ValueError(
            "Forecasts have been provided with differing forecast periods "
            f"{dtimes}"
        )


def align_forecast_truth_sta(
    forecast: pd.DataFrame,
    truth: pd.DataFrame,
    *,
    forecast_data_name: str,
    truth_data_name: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, np.ndarray]:
    """按 ``(level, id, 有效时间)`` 对齐，堆成内核可用数组。

    Returns
    -------
    fc_ltx, tr_ltx :
        ``(level, time, n_station)``，缺测为 NaN。
    thresholds, station_ids, lons, lats :
        阈值与站点元数据（与最后一维顺序一致）。
    dtime :
        单一时效（小时）。
    frts :
        每个 time 索引对应的起报时刻（长度 = time）。
    """
    f_lev = np.asarray(forecast["level"].values, dtype=np.float32)
    t_lev = np.asarray(truth["level"].values, dtype=np.float32)
    # 阈值集合须一致（float32 精确）
    if set(np.unique(f_lev).tolist()) != set(np.unique(t_lev).tolist()):
        raise ValueError("Threshold coordinates differ between forecasts and truths.")

    fc = add_valid_time(forecast)
    tr = add_valid_time(truth)
    fc = fc.rename(columns={forecast_data_name: "_fc_val"})
    tr = tr.rename(columns={truth_data_name: "_tr_val"})

    # 实况对齐键：level + id + valid_time；经纬度取预报侧
    merged = fc.merge(
        tr[["level", "id", "valid_time", "_tr_val"]],
        on=["level", "id", "valid_time"],
        how="inner",
    )
    if merged.empty:
        raise ValueError(
            "No matching validity times between historic forecasts and truths."
        )

    # 去掉整站全非有限的样本行（与网格「全无效切片跳过」类似，按行）
    valid_row = np.isfinite(merged["_fc_val"].to_numpy(dtype=np.float32))
    merged = merged.loc[valid_row]
    if merged.empty:
        raise ValueError(
            "No matching validity times between historic forecasts and truths."
        )

    thresholds = np.unique(np.asarray(merged["level"].values, dtype=np.float32))
    thresholds.sort()
    station_ids = np.unique(np.asarray(merged["id"].values, dtype=np.int32))
    station_ids.sort()
    # 每个起报时刻作为 time 轴一点（同一 FRT 下各站/阈值共享）
    frt_values = pd.to_datetime(np.unique(merged["time"].values))
    frt_values = np.sort(frt_values)

    dtime = float(np.asarray(merged["dtime"].values, dtype=np.float32)[0])
    # 站点 lon/lat：取预报中该 id 首次出现
    meta = (
        forecast.drop_duplicates(subset=["id"], keep="first")
        .set_index("id")
        .loc[station_ids]
    )
    lons = np.asarray(meta["lon"].values, dtype=np.float32)
    lats = np.asarray(meta["lat"].values, dtype=np.float32)

    n_lev, n_time, n_sta = thresholds.size, frt_values.size, station_ids.size
    fc_ltx = np.full((n_lev, n_time, n_sta), np.nan, dtype=np.float32)
    tr_ltx = np.full((n_lev, n_time, n_sta), np.nan, dtype=np.float32)

    lev_index = {float(v): i for i, v in enumerate(thresholds)}
    sta_index = {int(v): i for i, v in enumerate(station_ids)}
    frt_index = {pd.Timestamp(v): i for i, v in enumerate(frt_values)}

    levels_row = np.asarray(merged["level"].values, dtype=np.float32)
    ids_row = np.asarray(merged["id"].values, dtype=np.int32)
    frts_row = pd.to_datetime(merged["time"].values)
    fc_vals = np.asarray(merged["_fc_val"].values, dtype=np.float32)
    tr_vals = np.asarray(merged["_tr_val"].values, dtype=np.float32)
    for i in range(len(merged)):
        ilev = lev_index[float(levels_row[i])]
        it = frt_index[pd.Timestamp(frts_row[i])]
        ista = sta_index[int(ids_row[i])]
        fc_ltx[ilev, it, ista] = fc_vals[i]
        tr_ltx[ilev, it, ista] = tr_vals[i]

    return (
        fc_ltx,
        tr_ltx,
        thresholds,
        station_ids,
        lons,
        lats,
        dtime,
        frt_values,
    )


def reliability_long_table_from_array(
    stacked: np.ndarray,
    *,
    thresholds: np.ndarray,
    probability_bins: np.ndarray,
    station_ids: np.ndarray,
    lons: np.ndarray,
    lats: np.ndarray,
    time_point,
    time_bounds: Optional[Tuple] = None,
    dtime: float,
    relative_to_threshold: Optional[str] = None,
    spatial_kind: str = SPATIAL_KIND_STATION,
) -> pd.DataFrame:
    """由 ``(level, 3, n_bin, n_station)`` 构建可靠性长表。"""
    data = np.asarray(stacked, dtype=np.float32)
    n_lev, _, n_bin, n_sta = data.shape
    centers = np.mean(probability_bins, axis=1).astype(np.float32)
    time_point = pd.Timestamp(time_point)
    dtime = float(dtime)

    rows = []
    for ilev in range(n_lev):
        for ista in range(n_sta):
            for ibin in range(n_bin):
                rows.append(
                    {
                        "level": np.float32(thresholds[ilev]),
                        "time": time_point,
                        "dtime": np.float32(dtime),
                        "id": np.int32(station_ids[ista]),
                        "lon": np.float32(lons[ista]),
                        "lat": np.float32(lats[ista]),
                        "bin_index": np.int32(ibin),
                        "probability_bin": centers[ibin],
                        "probability_bin_bound_lower": np.float32(
                            probability_bins[ibin, 0]
                        ),
                        "probability_bin_bound_upper": np.float32(
                            probability_bins[ibin, 1]
                        ),
                        "observation_count": data[ilev, 0, ibin, ista],
                        "sum_of_forecast_probabilities": data[ilev, 1, ibin, ista],
                        "forecast_count": data[ilev, 2, ibin, ista],
                    }
                )
    out = pd.DataFrame(rows)
    out = _finalize_long_table_dtypes(out)
    out = out.sort_values(["level", "id", "bin_index"]).reset_index(drop=True)
    out.attrs = {
        "title": "Reliability calibration data table",
        "spatial_kind": spatial_kind,
    }
    if relative_to_threshold is not None:
        out.attrs["relative_to_threshold"] = relative_to_threshold
    if time_bounds is not None:
        out.attrs["time_bound_lower"] = pd.Timestamp(time_bounds[0])
        out.attrs["time_bound_upper"] = pd.Timestamp(time_bounds[1])
    return out


def _finalize_long_table_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["level"] = out["level"].astype(np.float32)
    out["time"] = pd.to_datetime(out["time"])
    out["dtime"] = out["dtime"].astype(np.float32)
    out["id"] = out["id"].astype(np.int32)
    out["lon"] = out["lon"].astype(np.float32)
    out["lat"] = out["lat"].astype(np.float32)
    out["bin_index"] = out["bin_index"].astype(np.int32)
    for col in (
        "probability_bin",
        "probability_bin_bound_lower",
        "probability_bin_bound_upper",
        *TABLE_ROW_NAMES,
    ):
        out[col] = out[col].astype(np.float32)
    return out


def aggregate_stations_to_sentinel(table: pd.DataFrame) -> pd.DataFrame:
    """对全部 ``id`` 求和，写成哨兵站 ``id=-1``。"""
    validate_reliability_table_sta(table)
    attrs = dict(table.attrs)
    gcols = ["level", "bin_index"]
    meta_first = (
        table.groupby(gcols, sort=True)[
            [
                "time",
                "dtime",
                "probability_bin",
                "probability_bin_bound_lower",
                "probability_bin_bound_upper",
            ]
        ]
        .first()
        .reset_index()
    )
    sums = (
        table.groupby(gcols, sort=True)[list(TABLE_ROW_NAMES)]
        .sum()
        .reset_index()
    )
    out = meta_first.merge(sums, on=gcols, how="inner")
    out["id"] = AGGREGATED_STATION_ID
    out["lon"] = np.float32(np.nan)
    out["lat"] = np.float32(np.nan)
    out = out[list(RELIABILITY_LONG_COLUMNS)]
    out = _finalize_long_table_dtypes(out)
    out = out.sort_values(["level", "id", "bin_index"]).reset_index(drop=True)
    attrs["spatial_kind"] = SPATIAL_KIND_AGGREGATED
    out.attrs = attrs
    return out


def validate_reliability_table_sta(df: pd.DataFrame) -> None:
    """检查可靠性长表列与基本约束。"""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"站点可靠性表须为 DataFrame，收到 {type(df)}")
    require_columns(df, RELIABILITY_LONG_COLUMNS)
    kind = df.attrs.get("spatial_kind")
    if kind not in (SPATIAL_KIND_STATION, SPATIAL_KIND_AGGREGATED, None):
        raise ValueError(f"未知 spatial_kind: {kind!r}")
    if kind == SPATIAL_KIND_AGGREGATED:
        ids = np.unique(np.asarray(df["id"].values, dtype=np.int32))
        if ids.size != 1 or int(ids[0]) != int(AGGREGATED_STATION_ID):
            raise ValueError(
                "spatial_kind=aggregated 时 id 须全部为哨兵 "
                f"{AGGREGATED_STATION_ID}"
            )


def table_frt_point_sta(df: pd.DataFrame) -> pd.Timestamp:
    return pd.Timestamp(np.atleast_1d(df["time"].values)[0])


def table_frt_bounds_sta(df: pd.DataFrame) -> Tuple[pd.Timestamp, pd.Timestamp]:
    lo = df.attrs.get("time_bound_lower")
    hi = df.attrs.get("time_bound_upper")
    if lo is None or hi is None:
        t = table_frt_point_sta(df)
        return t, t
    return pd.Timestamp(lo), pd.Timestamp(hi)


def probability_bins_from_long_table(df: pd.DataFrame) -> np.ndarray:
    """从某一 ``(level, id)`` 子集恢复箱边界（按 bin_index 排序）。"""
    sub = df.sort_values("bin_index")
    lower = np.asarray(sub["probability_bin_bound_lower"].values, dtype=np.float32)
    upper = np.asarray(sub["probability_bin_bound_upper"].values, dtype=np.float32)
    return np.stack([lower, upper], axis=1)


def _as_sta_table_list(
    tables: Union[pd.DataFrame, Sequence[pd.DataFrame]],
) -> List[pd.DataFrame]:
    if isinstance(tables, pd.DataFrame):
        return [tables]
    return list(tables)


def sum_station_reliability_tables(
    tables: Sequence[pd.DataFrame],
) -> pd.DataFrame:
    """多张站点可靠性长表按 ``(level, id, bin_index)`` 计数求和。"""
    if not tables:
        raise ValueError("sum_station_reliability_tables 需要至少一张表")
    for t in tables:
        validate_reliability_table_sta(t)

    kinds = {t.attrs.get("spatial_kind", SPATIAL_KIND_STATION) for t in tables}
    if len(kinds) != 1:
        raise ValueError(
            f"多表聚合要求 spatial_kind 一致，收到 {kinds}"
        )
    kind = next(iter(kinds)) or SPATIAL_KIND_STATION

    pieces = []
    for t in tables:
        pieces.append(t[list(RELIABILITY_LONG_COLUMNS)].copy())
    cat = pd.concat(pieces, ignore_index=True)
    gcols = ["level", "id", "bin_index"]
    meta = (
        cat.groupby(gcols, sort=True)[
            [
                "time",
                "dtime",
                "lon",
                "lat",
                "probability_bin",
                "probability_bin_bound_lower",
                "probability_bin_bound_upper",
            ]
        ]
        .first()
        .reset_index()
    )
    # time 取各表代表起报的最大
    meta["time"] = max(table_frt_point_sta(t) for t in tables)
    sums = cat.groupby(gcols, sort=True)[list(TABLE_ROW_NAMES)].sum().reset_index()
    out = meta.merge(sums, on=gcols, how="inner")
    out = out[list(RELIABILITY_LONG_COLUMNS)]
    out = _finalize_long_table_dtypes(out)
    out = out.sort_values(["level", "id", "bin_index"]).reset_index(drop=True)

    attrs = {
        "title": "Reliability calibration data table",
        "spatial_kind": kind,
    }
    rel = tables[0].attrs.get("relative_to_threshold")
    if rel is not None:
        attrs["relative_to_threshold"] = rel
    lows = [table_frt_bounds_sta(t)[0] for t in tables]
    ups = [table_frt_bounds_sta(t)[1] for t in tables]
    attrs["time_bound_lower"] = min(lows)
    attrs["time_bound_upper"] = max(ups)
    out.attrs = attrs
    return out
