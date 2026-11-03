#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形增强模块饱和水汽压辅助工具。

本模块存放自原 IMPROVER 饱和水汽压模块部分迁移的查表与计算逻辑，
供地形增强主算法中的格点增强项使用。

约定：除 ``calculate_svp_in_air`` 外，其余函数以下划线前缀命名，
表示模块私有，不应被外部直接导入。
"""

from __future__ import annotations

import functools

import numpy as np

ABSOLUTE_ZERO = -273.15  # 绝对零度，单位 °C
TRIPLE_PT_WATER = 273.16  # 水的三相点温度，单位 K
SVP_T_MIN = 183.15  # 饱和水汽压查表的最低温度，单位 K
SVP_T_MAX = 338.25  # 饱和水汽压查表的最高温度，单位 K
SVP_T_INCREMENT = 0.1  # 饱和水汽压查表的温度增量，单位 K


def _svp_pure_water_goff_gratch(temperature: np.ndarray) -> np.ndarray:
    """按 Goff-Gratch 公式计算纯水体系饱和水汽压。"""
    t = np.asarray(temperature, dtype=np.float64)
    triple_pt = float(TRIPLE_PT_WATER)
    over_triple = t > triple_pt
    n0_w = 10.79574 * (1.0 - triple_pt / t)
    n1_w = 5.028 * np.log10(t / triple_pt)
    n2_w = 1.50475e-4 * (1.0 - np.power(10.0, -8.2969 * (t / triple_pt - 1.0)))
    n3_w = 0.42873e-3 * (np.power(10.0, 4.76955 * (1.0 - triple_pt / t)) - 1.0)
    log_es_w = n0_w - n1_w + n2_w + n3_w + 0.78614
    es_w = np.power(10.0, log_es_w)
    n0_i = -9.09685 * (triple_pt / t - 1.0)
    n1_i = 3.56654 * np.log10(triple_pt / t)
    n2_i = 0.87682 * (1.0 - t / triple_pt)
    log_es_i = n0_i - n1_i + n2_i + 0.78614
    es_i = np.power(10.0, log_es_i)
    return np.where(over_triple, es_w, es_i)


@functools.lru_cache(maxsize=1)
def _svp_table() -> np.ndarray:
    """生成并缓存饱和水汽压查找表。"""
    temperatures = np.arange(SVP_T_MIN, SVP_T_MAX + 0.5 * SVP_T_INCREMENT, SVP_T_INCREMENT, dtype=np.float64)
    return _svp_pure_water_goff_gratch(temperatures) * 100.0


def _svp_from_lookup(temperature: np.ndarray) -> np.ndarray:
    """通过查表和线性插值得到饱和水汽压。

    参数
    ----------
    temperature : np.ndarray
        温度数组，单位为开尔文。

    返回值
    -------
    np.ndarray
        饱和水汽压，单位为帕。
    """
    # 用查表加线性插值近似饱和水汽压，避免逐点重复计算经验公式。
    t_clipped = np.clip(temperature, SVP_T_MIN, SVP_T_MAX - SVP_T_INCREMENT)
    t_clipped = np.nan_to_num(
        t_clipped,
        nan=SVP_T_MIN,
        posinf=SVP_T_MAX - SVP_T_INCREMENT,
        neginf=SVP_T_MIN,
    )
    table_position = (t_clipped - SVP_T_MIN) / SVP_T_INCREMENT
    table_index = table_position.astype(int)
    interpolation_factor = table_position - table_index
    svp_table = _svp_table()
    table_index = np.clip(table_index, 0, len(svp_table) - 2)
    return (1.0 - interpolation_factor) * svp_table[table_index] + interpolation_factor * svp_table[table_index + 1]


def calculate_svp_in_air(temperature: np.ndarray, pressure: np.ndarray) -> np.ndarray:
    """计算湿空气中的饱和水汽压。

    参数
    ----------
    temperature : np.ndarray
        温度数组，单位为开尔文。
    pressure : np.ndarray
        气压数组，单位为帕。

    返回值
    -------
    np.ndarray
        湿空气中的饱和水汽压，单位为帕。
    """
    # 先求纯水饱和水汽压，再按气压做湿空气修正。
    svp = _svp_from_lookup(temperature)
    temp_c = temperature + ABSOLUTE_ZERO
    correction = 1.0 + 1.0e-8 * pressure * (4.5 + 6.0e-4 * temp_c * temp_c)
    return svp * correction.astype(np.float32)
