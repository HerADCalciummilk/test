#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""偏差订正模块私有辅助（由 IMPROVER calibration utilities 迁移）。

meb 约定：起报为 ``time``，预测周期为 ``dtime``（小时）；有效时刻 = time + dtime。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr
from cf_units import Unit as CfUnit
from numpy import ndarray

MANDATORY_ATTRIBUTES = ("title", "source", "institution")
MANDATORY_ATTRIBUTE_DEFAULTS = {
    "title": "unknown",
    "source": "IMPROVER",
    "institution": "unknown",
}


def dataarray_units(data: xr.DataArray) -> Optional[str]:
    """读取 DataArray 主变量 ``attrs['units']``；缺失或空串时返回 ``None``。"""
    units = data.attrs.get("units")
    if units is None:
        return None
    text = str(units).strip()
    return text or None


def convert_array_to_units(
    values: ndarray,
    from_units: Optional[str],
    to_units: Optional[str],
) -> ndarray:
    """将数组数值从 ``from_units`` 换算到 ``to_units``。

    任一侧无单位，或两侧相同，则原样返回。不可换算时抛 ``ValueError``。
    """
    if from_units is None or to_units is None or from_units == to_units:
        return np.asarray(values, dtype=float)
    try:
        src = CfUnit(from_units)
        dst = CfUnit(to_units)
    except Exception as err:
        raise ValueError(
            f"无法解析单位: from={from_units!r}, to={to_units!r}"
        ) from err
    if not src.is_convertible(dst):
        raise ValueError(
            f"单位不兼容，无法换算: {from_units!r} -> {to_units!r}"
        )
    flat = np.asarray(values, dtype=np.float64).ravel()
    converted = src.convert(flat, dst)
    return converted.reshape(np.asarray(values).shape)


def align_operand_units_to_reference(
    operand: xr.DataArray,
    reference: xr.DataArray,
) -> ndarray:
    """将 ``operand`` 数值换算到 ``reference`` 的 ``attrs['units']``（若双方均有单位）。"""
    ref_units = dataarray_units(reference)
    op_units = dataarray_units(operand)
    values = np.asarray(operand.values, dtype=float)
    return convert_array_to_units(values, op_units, ref_units)


def is_probability_named_dataarray(data: xr.DataArray) -> bool:
    """按 IMPROVER / threshold 命名约定判断是否为概率场（弱规则）。

    单阈值概率在 meb 中 ``level`` 长度可为 1，无法仅靠维长识别；变量名以
    ``probability_of_`` 开头时视为概率数据并拒绝用于偏差计算。
    """
    return str(data.name or "").startswith("probability_of_")


def _as_datetime64_scalar(value) -> np.datetime64:
    """将标量时间值转为 datetime64[ns]。"""
    return np.datetime64(pd.Timestamp(value).to_datetime64())


def _coord_hours(values) -> Set[int]:
    """从起报坐标值提取小时集合。"""
    arr = np.atleast_1d(np.asarray(values))
    hours: Set[int] = set()
    for item in arr.ravel():
        hours.add(int(pd.Timestamp(item).hour))
    return hours


def get_frt_hours(time_coord: Union[xr.DataArray, np.ndarray]) -> Set[int]:
    """返回起报 ``time`` 坐标中出现的小时集合。"""
    if isinstance(time_coord, xr.DataArray):
        return _coord_hours(time_coord.values)
    return _coord_hours(time_coord)


def _dtime_hours(dtime_val) -> float:
    """将 ``dtime`` 标量解释为小时。"""
    arr = np.asarray(dtime_val, dtype=float).ravel()
    if arr.size != 1:
        raise ValueError(
            f"dtime 须为单一时效值，当前有 {arr.size} 个: {arr}"
        )
    return float(arr[0])


def _dtime_as_timedelta(dtime_val) -> np.timedelta64:
    """``dtime``（小时）→ timedelta。"""
    hours = _dtime_hours(dtime_val)
    # 用秒避免非整数小时精度问题
    return np.timedelta64(int(round(hours * 3600.0)), "s")


def _dtime_candidates(data: xr.DataArray, time_val) -> List[float]:
    """列出某个起报下待遍历的 ``dtime``（小时）取值。"""
    if "dtime" not in data.coords:
        raise ValueError("数据缺少 dtime 坐标。")
    dtime = data["dtime"]
    if "dtime" in data.dims:
        # 独立 dtime 维：与该 time 组合的全部时效
        if "time" in dtime.dims:
            vals = data.sel(time=time_val)["dtime"].values
        else:
            vals = dtime.values
        return [float(v) for v in np.atleast_1d(vals).ravel()]
    # 标量或仅随 time 变化的辅助坐标：每个起报一个时效
    if "time" in getattr(dtime, "dims", ()):
        vals = data.sel(time=time_val)["dtime"].values
    else:
        vals = dtime.values
    arr = np.atleast_1d(np.asarray(vals, dtype=float)).ravel()
    if arr.size == 0:
        raise ValueError("dtime 坐标为空。")
    if arr.size > 1:
        # 非维坐标却多值：无法唯一确定样本，拒绝
        raise ValueError(
            f"非维度 dtime 出现多个值 {arr}，无法与 time 一一对应。"
        )
    return [float(arr[0])]


def valid_time_of(
    data: xr.DataArray, time_val, dtime_val=None
) -> np.datetime64:
    """计算有效时刻：起报 ``time`` + ``dtime``（小时）。

    ``dtime_val`` 给定时用该时效；否则要求数据在该起报下仅有一个 dtime。
    """
    frt = _as_datetime64_scalar(time_val)
    if dtime_val is None:
        cands = _dtime_candidates(data, time_val)
        if len(cands) != 1:
            raise ValueError(
                "未指定 dtime_val 且存在多个时效，无法计算唯一有效时刻。"
            )
        dtime_val = cands[0]
    return frt + _dtime_as_timedelta(dtime_val)


def ensure_meb6d(data: xr.DataArray) -> xr.DataArray:
    """补齐 meb 前四维 ``member, level, time, dtime`` 为长度 1，空间维保持在后。

    已有长度为 1 的对应维则保留；缺失维时从标量坐标取值，或使用默认
    ``member=0`` / ``level=0.0``。``time`` / ``dtime`` 必须已存在于坐标中。
    """
    result = data
    for dim in ("member", "level", "time", "dtime"):
        if dim in result.dims:
            if result.sizes[dim] != 1:
                raise ValueError(
                    f"偏差场输出要求 {dim} 长度为 1，当前为 {result.sizes[dim]}。"
                )
            continue
        if dim in result.coords:
            val = np.atleast_1d(np.asarray(result[dim].values)).ravel()[0]
            result = result.expand_dims({dim: [val]})
        elif dim == "member":
            result = result.expand_dims(member=[0])
        elif dim == "level":
            result = result.expand_dims(level=[0.0])
        else:
            raise ValueError(f"偏差场缺少 {dim} 坐标，无法补齐 meb 六维。")

    spatial = [d for d in result.dims if d not in ("member", "level", "time", "dtime")]
    return result.transpose(*("member", "level", "time", "dtime"), *spatial)


def check_forecast_consistency(forecasts: xr.DataArray) -> None:
    """检查历史预报的起报小时（``time``）与 ``dtime`` 是否一致。

    对齐原版：``dtime`` / forecast_period 必须只有 **一个点**（维长为 1 或标量）。
    """
    if "time" not in forecasts.coords:
        raise ValueError("预报缺少 time 坐标。")
    if "dtime" not in forecasts.coords:
        raise ValueError("预报缺少 dtime 坐标。")

    frt_hours = get_frt_hours(forecasts["time"])
    if len(frt_hours) != 1:
        raise ValueError(
            "Forecasts have been provided with differing hours for the "
            f"forecast reference time {set(map(int, frt_hours))}"
        )

    if "dtime" in forecasts.dims and forecasts.sizes["dtime"] != 1:
        raise ValueError(
            "Forecasts have been provided with differing forecast periods "
            f"{np.asarray(forecasts['dtime'].values).ravel()}"
        )

    period_vals = np.atleast_1d(np.asarray(forecasts["dtime"].values).ravel())
    if period_vals.size != 1:
        raise ValueError(
            "Forecasts have been provided with differing forecast periods "
            f"{period_vals}"
        )


def _constrain_time_dtime(
    data: xr.DataArray, time_val, dtime_val: float
) -> xr.DataArray:
    """截取单个历史样本：``time`` 与 ``dtime`` 同时约束为长度 1。"""
    frt64 = _as_datetime64_scalar(time_val)
    dt = float(dtime_val)

    out = data
    if "time" in out.dims:
        out = out.sel(time=time_val, drop=True)
    if "dtime" in out.dims:
        out = out.sel(dtime=dt, drop=True)
    # 去掉残留标量坐标，再扩成长度 1 的维
    drop_scalar = [
        name
        for name in ("time", "dtime")
        if name in out.coords and name not in out.dims
    ]
    if drop_scalar:
        out = out.drop_vars(drop_scalar)

    out = out.expand_dims(time=[frt64], dtime=[np.float32(dt)])
    return out


def filter_non_matching_by_valid_time(
    historic_forecast: xr.DataArray, truth: xr.DataArray
) -> Tuple[xr.DataArray, xr.DataArray]:
    """按有效时刻对齐历史预报与实况，丢弃无法配对的 ``(time, dtime)`` 组合。

    对应原版 ``filter_non_matching_cubes``（iris Cube）；此处输入为 meb
    ``xarray.DataArray``。调用方应先用 ``meb.checkout_griddata`` 保证标准六维，
    因此 ``time`` / ``dtime`` 须已是维度（可为长度 1）。

    有效时刻 = ``time``（起报）+ ``dtime``（小时）。对每个 ``(time, dtime)``
    组合分别匹配；成功后将该组合截为单样本（两维长度均为 1），再沿 ``time``
    拼成多日历史维。首次成功匹配会锁定起报钟点与时效，后续只保留同一钟点、
    同一 ``dtime`` 的样本。

    若某个预报切片全为 NaN，则跳过。同一实况有效时刻只保留第一次匹配。

    Raises
    ------
    ValueError
        缺少 ``time`` 维，或没有任何共同有效时刻。
    """
    if "time" not in historic_forecast.dims:
        raise ValueError("预报缺少 time 维；请先经 meb.checkout_griddata 校验。")
    if "time" not in truth.dims:
        raise ValueError("实况缺少 time 维；请先经 meb.checkout_griddata 校验。")

    hf = historic_forecast
    tr = truth

    # 实况：valid → (truth_time, truth_dtime)
    truth_valid_map: Dict[np.datetime64, Tuple[np.datetime64, float]] = {}
    for t_val in tr["time"].values:
        for dt in _dtime_candidates(tr, t_val):
            v = valid_time_of(tr, t_val, dt)
            truth_valid_map.setdefault(
                v, (_as_datetime64_scalar(t_val), float(dt))
            )

    matched_hf: List[xr.DataArray] = []
    matched_tr: List[xr.DataArray] = []
    used_truth_valids: Set[np.datetime64] = set()
    locked_dtime: Optional[float] = None
    locked_hour: Optional[int] = None

    for t_val in hf["time"].values:
        frt64 = _as_datetime64_scalar(t_val)
        frt_hour = int(pd.Timestamp(frt64).hour)
        for dt in _dtime_candidates(hf, t_val):
            if locked_dtime is not None and (
                float(dt) != locked_dtime or frt_hour != locked_hour
            ):
                continue
            hf_slice = _constrain_time_dtime(hf, t_val, dt)
            if np.isnan(np.asarray(hf_slice.values, dtype=float)).all():
                continue
            valid = valid_time_of(hf, t_val, dt)
            if valid not in truth_valid_map or valid in used_truth_valids:
                continue
            tr_time, tr_dt = truth_valid_map[valid]
            tr_slice = _constrain_time_dtime(tr, tr_time, tr_dt)
            # 实况 time 改标为预报起报，便于沿 time 与预报对齐相减
            tr_slice = tr_slice.assign_coords(time=[frt64])
            used_truth_valids.add(valid)
            if locked_dtime is None:
                locked_dtime = float(dt)
                locked_hour = frt_hour
            matched_hf.append(hf_slice)
            matched_tr.append(tr_slice)

    if not matched_hf:
        raise ValueError(
            "The filtering has found no matches in validity time "
            "between the historic forecasts and the truths."
        )

    return (
        xr.concat(matched_hf, dim="time", coords="different", compat="equals"),
        xr.concat(matched_tr, dim="time", coords="different", compat="equals"),
    )


def create_unified_time_values(
    time_coord: xr.DataArray,
    *,
    existing_bounds: Optional[Sequence] = None,
) -> Tuple[np.datetime64, Optional[np.ndarray]]:
    """由多值起报 ``time`` 构造统一的 point 与 bounds。

    Parameters
    ----------
    time_coord :
        起报时间坐标（可多值）。
    existing_bounds :
        可选的既有 ``[min, max]`` bounds（例如来自 attrs）。

    Returns
    -------
    time_point
        输入起报的最大值（最新起报）。
    time_bounds
        shape ``(2,)`` 的 ``[min, max]``；仅单个起报且无既有 bounds 时为 ``None``。
    """
    values = np.array(
        [_as_datetime64_scalar(v) for v in np.atleast_1d(time_coord.values).ravel()]
    )
    time_point = values.max()
    bounds_min = values.min()
    bounds_max = time_point

    # 坐标上的 time_bounds
    if "time_bounds" in time_coord.coords:
        b = np.array(
            [
                _as_datetime64_scalar(v)
                for v in np.asarray(time_coord.coords["time_bounds"].values).ravel()
            ]
        )
        bounds_min = min(bounds_min, b.min())
        bounds_max = max(bounds_max, b.max())
        return time_point, np.array([bounds_min, bounds_max], dtype="datetime64[ns]")

    if existing_bounds is not None:
        b = np.array([_as_datetime64_scalar(v) for v in np.asarray(existing_bounds).ravel()])
        bounds_min = min(bounds_min, b.min())
        bounds_max = max(bounds_max, b.max())
        return time_point, np.array([bounds_min, bounds_max], dtype="datetime64[ns]")

    if values.size == 1:
        return time_point, None
    return time_point, np.array([bounds_min, bounds_max], dtype="datetime64[ns]")


def has_time_bounds(data: xr.DataArray) -> bool:
    """判断偏差场是否带有**有效**起报 ``time_bounds``（attrs 或坐标）。

    ``meb.set_griddata_attrs(..., is_default=True)`` / ``checkout_griddata``
    可能写入占位 ``[0, 0]``，不视为多日起报范围。
    """
    bounds = data.attrs.get("time_bounds")
    if bounds is not None and _is_real_time_bounds(bounds):
        return True
    if "time_bounds" in data.coords:
        return _is_real_time_bounds(data.coords["time_bounds"].values)
    return False


def _is_real_time_bounds(bounds) -> bool:
    """排除空值与 meb 缺省占位 ``[0, 0]``。"""
    if bounds is None:
        return False
    arr = np.asarray(bounds).ravel()
    if arr.size < 2:
        return False
    # meb 默认占位：两个 0（int / float）
    try:
        as_float = arr.astype(np.float64)
        if np.allclose(as_float, 0.0):
            return False
    except (TypeError, ValueError):
        pass
    return True


def strip_placeholder_time_bounds(data: xr.DataArray) -> xr.DataArray:
    """去掉 attrs 中的 meb 占位 ``time_bounds``（就地改 attrs，返回同一对象）。"""
    bounds = data.attrs.get("time_bounds")
    if bounds is not None and not _is_real_time_bounds(bounds):
        data.attrs.pop("time_bounds", None)
    return data


def split_forecasts_and_bias(
    inputs: Sequence[xr.DataArray],
) -> Tuple[xr.DataArray, Optional[List[xr.DataArray]]]:
    """从输入列表拆出当前预报与偏差场。

    名称中含 ``forecast_error`` 的视为偏差；其余视为预报（仅允许一个）。

    Raises
    ------
    ValueError
        无预报，或多个预报。
    """
    forecast: Optional[xr.DataArray] = None
    bias_list: List[xr.DataArray] = []
    for item in inputs:
        name = str(item.name or "")
        if "forecast_error" in name:
            bias_list.append(item)
        else:
            if forecast is None:
                forecast = item
            else:
                raise ValueError(
                    "Multiple forecast inputs have been provided. Only one is expected."
                )
    if forecast is None:
        raise ValueError("No forecast is present. A forecast DataArray is required.")
    return forecast, (bias_list if bias_list else None)


def add_warning_comment(forecast: xr.DataArray) -> xr.DataArray:
    """在 attrs['comment'] 中追加未订正警告。"""
    result = forecast.copy(deep=True)
    warning = (
        "Warning: Calibration of this forecast has been attempted, "
        "however, no calibration has been applied."
    )
    existing = result.attrs.get("comment")
    if existing:
        result.attrs["comment"] = f"{existing}\n{warning}"
    else:
        result.attrs["comment"] = warning
    return result


def clip_dataarray(
    data: xr.DataArray,
    minimum_value: Optional[float],
    maximum_value: Optional[float],
) -> xr.DataArray:
    """对 DataArray 数值做上下界裁剪（``None`` 表示该侧不限制）。"""
    lo = minimum_value if minimum_value is not None else -np.inf
    hi = maximum_value if maximum_value is not None else np.inf
    result = data.copy(deep=True)
    result.data = np.clip(np.asarray(result.values, dtype=result.dtype), lo, hi)
    return result


def generate_mandatory_attributes(
    data_arrays: Sequence[xr.DataArray],
) -> Dict[str, str]:
    """从输入场收集 IMPROVER 强制属性；不一致则用默认值。"""
    attributes = dict(MANDATORY_ATTRIBUTE_DEFAULTS)
    attr_dicts = [dict(da.attrs) for da in data_arrays]
    for attr in MANDATORY_ATTRIBUTES:
        unique_values = {d.get(attr, None) for d in attr_dicts}
        if len(unique_values) == 1 and None not in unique_values:
            (attributes[attr],) = unique_values
    return attributes
