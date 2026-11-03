#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""ApplyOrographicEnhancement 插件内部工具。

本模块存放降水叠加/扣除插件所需的单位转换、时间匹配等私有辅助函数。

约定：所有函数以下划线前缀命名，表示模块私有，不应被外部直接导入。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
from cf_units import Unit


def _threshold_in_units(units: str, min_precip_rate_mmh: float) -> float:
    """将最小降水率阈值（mm/h）转换到目标单位。"""
    target_units = (units or "").strip() or "mm/hr"
    return float(Unit("mm/hr").convert(min_precip_rate_mmh, Unit(target_units)))


def _to_datetime64(value: object) -> Optional[np.datetime64]:
    """将标量时间值标准化为 ``np.datetime64``。"""
    if value is None:
        return None
    if isinstance(value, np.datetime64):
        return value
    if isinstance(value, datetime):
        return np.datetime64(value)
    try:
        return np.datetime64(value)
    except Exception:
        return None


def _extract_scalar_time_value(time_value: object) -> object:
    """提取 time 坐标中的标量时间值。"""
    values = np.asarray(time_value)
    if values.ndim == 0:
        return values.item()
    if values.size == 1:
        return values.reshape(-1)[0]
    raise ValueError("降水输入 time 坐标包含多个时次，无法匹配单个地形增强时次")


def _nearest_time_index(
    target_time: np.datetime64, candidates: np.ndarray, allowed_time_diff: int
) -> int:
    """在候选时间中查找最近时刻索引。"""
    candidate_time = candidates.astype("datetime64[s]")
    target_s = target_time.astype("datetime64[s]")
    abs_delta_s = np.abs((candidate_time - target_s).astype("timedelta64[s]").astype(np.int64))
    best_idx = int(np.argmin(abs_delta_s))
    if int(abs_delta_s[best_idx]) > int(allowed_time_diff):
        raise ValueError(
            "未找到满足时间容差的地形增强时次："
            f"最小时间差 {int(abs_delta_s[best_idx])}s，允许 {int(allowed_time_diff)}s"
        )
    return best_idx
