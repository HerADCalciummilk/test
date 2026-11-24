# -*- coding: utf-8 -*-
"""层结递减率辅助计算。插件调用本模块，不改数值公式。"""
import numpy as np

# 环境递减率（标准大气），单位 K/m
ELR = -0.0065


def compute_lapse_rate_adjustment(
    lapse_rate: np.ndarray,
    orog_diff: np.ndarray,
    max_orog_diff_limit: float = 50.0,
) -> np.ndarray:
    """根据层结递减率与地形高度差计算温度订正量。

    计算逻辑：
    1. 当高度差绝对值不超过 `max_orog_diff_limit` 时，使用 `lapse_rate * orog_diff`；
    2. 超过上限的高度差部分使用环境递减率 `ELR`，避免订正量异常放大。
    """
    orog_diff = np.broadcast_to(orog_diff, lapse_rate.shape).copy()
    orig_orog_diff = orog_diff.copy()

    # 高度差超过上限的部分改用环境递减率，避免未解析山顶或山谷把订正量放大
    condition1 = orog_diff > max_orog_diff_limit
    condition2 = orog_diff < -max_orog_diff_limit
    orog_diff[condition1] = max_orog_diff_limit
    orog_diff[condition2] = -max_orog_diff_limit
    vertical_adjustment = np.multiply(orog_diff, lapse_rate)

    orig_orog_diff[condition1] = np.clip(
        orig_orog_diff[condition1] - max_orog_diff_limit, 0, None
    )
    orig_orog_diff[condition2] = np.clip(
        orig_orog_diff[condition2] + max_orog_diff_limit, None, 0
    )

    vertical_adjustment[condition1] += np.multiply(orig_orog_diff[condition1], ELR)
    vertical_adjustment[condition2] += np.multiply(orig_orog_diff[condition2], ELR)
    return vertical_adjustment
