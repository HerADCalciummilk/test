# -*- coding: utf-8 -*-
"""阵风系数的回归与风速到阵风的换算。读写不在这里。"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np


def origin_scale(obs_arr: np.ndarray, fore_arr: np.ndarray) -> float:
    """过原点最小二乘：param = Σ(obs·fcst) / Σ(fcst²)。"""
    return float(np.sum(obs_arr * fore_arr) / np.sum(fore_arr * fore_arr))


def percent_values(data_arr, per_list: Sequence[int]) -> List[float]:
    """按百分位序列取值，忽略 NaN。"""
    data_arr = np.asarray(data_arr, dtype=float)
    filtered_arr = data_arr[~np.isnan(data_arr)]
    return [float(np.percentile(filtered_arr, p_v)) for p_v in per_list]


def least_squares(x, y) -> Tuple[float, float]:
    """一元线性最小二乘 ``y = a·x + b``。"""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mean_x = np.mean(x)
    mean_y = np.mean(y)
    denominator = np.sum((x - mean_x) ** 2)
    # 退化情形：分位几乎常数，退回单位斜率
    if denominator == 0:
        return 1.0, float(mean_y - mean_x)
    a = float(np.sum((x - mean_x) * (y - mean_y)) / denominator)
    b = float(mean_y - a * mean_x)
    return a, b


def gust_from_wind(s_arr, param: float, a: float, b: float) -> np.ndarray:
    """平均风速 → 订正阵风，并做负值、过大值与不低于风速的约束。"""
    gust_arr = s_arr * float(param)
    new_g_arr = gust_arr * float(a) + float(b)
    # 负值或异常大值回退到未匹配的 gust_arr
    new_g_arr = np.where(new_g_arr < 0, gust_arr, new_g_arr)
    new_g_arr = np.where(new_g_arr > 100, gust_arr, new_g_arr)
    # 阵风不应低于同时次平均风速
    min_mask = new_g_arr < s_arr
    new_g_arr = new_g_arr.copy()
    new_g_arr[min_mask] = s_arr[min_mask]
    return new_g_arr
