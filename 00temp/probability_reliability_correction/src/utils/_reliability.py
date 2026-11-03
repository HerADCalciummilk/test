#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""网格路径的 meb 适配与可靠性表（三变量 × 六维）组装辅助。

数值核心（归箱、并箱、插值）在 ``construct`` / ``manipulate`` / ``apply``；
本模块只做坐标对齐与 Dataset 组装。

    可靠性表约定（融入 nimm / meb）：
- 一张表 = ``xr.Dataset``，含三个六维变量
  ``observation_count`` / ``sum_of_forecast_probabilities`` / ``forecast_count``
- 每个变量 dims = ``member, level, time, dtime, lat, lon``
- ``member``：概率箱（辅坐标挂箱中点与上下界）
- ``level``：诊断阈值
- ``time`` / ``dtime``：统一起报代表点与单一时效（长度通常为 1）
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

import meteva_base as meb

# 可靠性表三变量
TABLE_ROW_NAMES = (
    "observation_count",
    "sum_of_forecast_probabilities",
    "forecast_count",
)


def meb_valid_times(da: xr.DataArray) -> np.ndarray:
    """有效时间，形状 ``(time, dtime)``。"""
    times = pd.to_datetime(np.atleast_1d(da["time"].values))
    dtimes = np.atleast_1d(da["dtime"].values).astype(np.float64)
    return np.array(
        [
            [t + pd.to_timedelta(float(dt), unit="h") for dt in dtimes]
            for t in times
        ]
    )


def frt_hours(da: xr.DataArray) -> set:
    """起报时间的小时集合。"""
    times = pd.to_datetime(np.atleast_1d(da["time"].values))
    return {int(t.hour) for t in times}


def check_forecast_consistency_meb(forecast: xr.DataArray) -> None:
    """检查预报 FRT 钟点唯一且 ``dtime`` 唯一。"""
    hours = frt_hours(forecast)
    if len(hours) != 1:
        raise ValueError(
            "Forecasts have been provided with differing hours for the "
            f"forecast reference time {hours}"
        )
    if forecast.sizes["dtime"] != 1:
        raise ValueError(
            "Forecasts have been provided with differing forecast periods "
            f"{forecast['dtime'].values}"
        )


def align_forecast_truth_meb(
    forecast: xr.DataArray, truth: xr.DataArray
) -> Tuple[xr.DataArray, xr.DataArray]:
    """按有效时间对齐预报与实况，输出仍为 meb 六维（匹配样本堆在 time 维）。"""
    # 与原版 Iris 阈值坐标精确相等一致：统一 float32 后再比，避免 isclose 误匹配邻近阈值
    f_lev = np.asarray(forecast["level"].values, dtype=np.float32)
    t_lev = np.asarray(truth["level"].values, dtype=np.float32)
    if f_lev.shape != t_lev.shape or not np.array_equal(f_lev, t_lev):
        raise ValueError("Threshold coordinates differ between forecasts and truths.")

    f_valid = meb_valid_times(forecast)
    t_valid = meb_valid_times(truth)
    t_map = {}
    for i in range(t_valid.shape[0]):
        for j in range(t_valid.shape[1]):
            key = pd.Timestamp(t_valid[i, j])
            if key not in t_map:
                t_map[key] = (i, j)

    matched = []
    used_truth = set()
    for i in range(f_valid.shape[0]):
        for j in range(f_valid.shape[1]):
            fv = pd.Timestamp(f_valid[i, j])
            if fv not in t_map or fv in used_truth:
                continue
            sl = forecast.isel(member=0, time=i, dtime=j)
            if np.all(~np.isfinite(np.asarray(sl.values, dtype=float))):
                continue
            ti, tj = t_map[fv]
            used_truth.add(fv)
            matched.append((i, j, ti, tj))

    if not matched:
        raise ValueError(
            "No matching validity times between historic forecasts and truths."
        )

    dtime_val = float(forecast["dtime"].values[matched[0][1]])
    f_blocks = []
    t_blocks = []
    new_frts = []
    for fi, fj, ti, tj in matched:
        f_blocks.append(forecast.isel(time=fi, dtime=fj).values)
        t_blocks.append(truth.isel(time=ti, dtime=tj).values)
        new_frts.append(pd.Timestamp(forecast["time"].values[fi]))

    f_arr = np.stack(f_blocks, axis=0)
    t_arr = np.stack(t_blocks, axis=0)
    f_arr = np.transpose(f_arr, (1, 2, 0, 3, 4))
    t_arr = np.transpose(t_arr, (1, 2, 0, 3, 4))
    f_arr = f_arr[:, :, :, np.newaxis, :, :]
    t_arr = t_arr[:, :, :, np.newaxis, :, :]

    coords = {
        "member": forecast["member"].values,
        "level": forecast["level"].values,
        "time": new_frts,
        "dtime": np.array([dtime_val]),
        "lat": forecast["lat"].values,
        "lon": forecast["lon"].values,
    }
    forecast_out = xr.DataArray(
        f_arr.astype(np.float32),
        coords=coords,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=forecast.name,
        attrs=dict(forecast.attrs),
    )
    truth_out = xr.DataArray(
        t_arr.astype(np.float32),
        coords=coords,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        name=truth.name,
        attrs=dict(truth.attrs),
    )
    return forecast_out, truth_out


def reliability_table_from_array(
    data: np.ndarray,
    *,
    thresholds: np.ndarray,
    probability_bins: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    time_point,
    time_bounds: Optional[Tuple] = None,
    dtime: float,
    relative_to_threshold: Optional[str] = None,
    attrs: Optional[dict] = None,
) -> xr.Dataset:
    """由 ``(threshold, 3, n_bin, lat, lon)`` 构建三变量 meb 六维可靠性表。

    维映射：
    - ``member`` ← 概率箱
    - ``level`` ← 诊断阈值
    - ``time`` / ``dtime`` ← 统一起报代表点与单一时效（长度 1）
    - ``lat`` / ``lon`` ← 空间
    """
    data = np.asarray(data, dtype=np.float32)
    _, _, n_bin, _, _ = data.shape
    centers = np.mean(probability_bins, axis=1).astype(np.float32)
    member = np.arange(n_bin, dtype=np.int32)
    level = np.asarray(thresholds, dtype=np.float32)
    time_coord = np.array([pd.Timestamp(time_point)])
    dtime_coord = np.array([float(dtime)], dtype=np.float32)
    lat = np.asarray(lat, dtype=np.float32)
    lon = np.asarray(lon, dtype=np.float32)

    base_coords = {
        "member": member,
        "level": level,
        "time": time_coord,
        "dtime": dtime_coord,
        "lat": lat,
        "lon": lon,
        "probability_bin": ("member", centers),
        "probability_bin_bound_lower": ("member", probability_bins[:, 0]),
        "probability_bin_bound_upper": ("member", probability_bins[:, 1]),
    }
    if time_bounds is not None:
        base_coords["time_bound_lower"] = pd.Timestamp(time_bounds[0])
        base_coords["time_bound_upper"] = pd.Timestamp(time_bounds[1])

    data_vars = {}
    for i, name in enumerate(TABLE_ROW_NAMES):
        # (threshold, n_bin, lat, lon) -> (member, level, lat, lon)
        arr = np.transpose(data[:, i], (1, 0, 2, 3))
        arr = arr[:, :, np.newaxis, np.newaxis, :, :]
        da = xr.DataArray(
            arr,
            coords=base_coords,
            dims=("member", "level", "time", "dtime", "lat", "lon"),
            name=name,
            attrs={"units": "1", "title": "Reliability calibration data table"},
        )
        if relative_to_threshold is not None:
            da.attrs["relative_to_threshold"] = relative_to_threshold
        if attrs:
            da.attrs.update(attrs)
        data_vars[name] = da

    ds = xr.Dataset(data_vars, attrs={"title": "Reliability calibration data table"})
    if relative_to_threshold is not None:
        ds.attrs["relative_to_threshold"] = relative_to_threshold
    if attrs:
        ds.attrs.update(attrs)
    return ds


def ensure_meb_spatial_size_one(ds: xr.Dataset, template: xr.Dataset) -> xr.Dataset:
    """空间求和后若缺少 lat/lon 维，补长度为 1 的维以保持 meb 六维。"""
    out = {}
    lat_c = float(np.mean(np.asarray(template["lat"].values, dtype=float)))
    lon_c = float(np.mean(np.asarray(template["lon"].values, dtype=float)))
    for name in TABLE_ROW_NAMES:
        da = ds[name]
        if "lat" not in da.dims:
            da = da.expand_dims(lat=[lat_c])
        if "lon" not in da.dims:
            da = da.expand_dims(lon=[lon_c])
        # 保留 member 上的概率箱辅坐标
        for cname in (
            "probability_bin",
            "probability_bin_bound_lower",
            "probability_bin_bound_upper",
        ):
            if cname in template.coords and cname not in da.coords:
                da = da.assign_coords({cname: template[cname]})
        da = da.transpose("member", "level", "time", "dtime", "lat", "lon")
        out[name] = da
    result = xr.Dataset(out, attrs=dict(ds.attrs))
    for key in ("time_bound_lower", "time_bound_upper"):
        if key in ds.coords:
            result = result.assign_coords({key: ds[key]})
        elif key in template.coords:
            result = result.assign_coords({key: template[key]})
    return result


def probability_bins_from_dataset(ds: xr.Dataset) -> np.ndarray:
    """从 member 辅坐标恢复 ``(n_bin, 2)`` 边界。"""
    lower = np.asarray(ds["probability_bin_bound_lower"].values, dtype=np.float32)
    upper = np.asarray(ds["probability_bin_bound_upper"].values, dtype=np.float32)
    return np.stack([lower, upper], axis=1)


def table_frt_point(ds: xr.Dataset) -> pd.Timestamp:
    """读取表上代表起报时刻。"""
    return pd.Timestamp(np.atleast_1d(ds["time"].values)[0])


def validate_reliability_table_meb(ds: xr.Dataset) -> None:
    """检查可靠性表三变量均为 meb 六维。"""
    
    for name in TABLE_ROW_NAMES:
        if name not in ds:
            raise ValueError(f"可靠性表缺少变量 {name}")
        meb.checkout_griddata(ds[name], valid_val=(-np.inf, np.inf, np.nan))
