#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""体感温度模块内部工具函数。

本模块存放仅服务于 ``feels_like_temperature`` 核心算法的私有辅助实现：
- 网格输入校验（私有）
- 饱和水汽压查表与计算（私有，供显温公式使用）

约定：所有函数以下划线前缀命名，表示模块私有，不应被外部直接导入。
"""

from __future__ import annotations

import functools
from typing import Optional, Union

import numpy as np
import xarray as xr

import meteva_base as meb


#: 0 开尔文对应的摄氏温标偏移
ABSOLUTE_ZERO = -273.15

#: 水的三相点温度，单位为 K
TRIPLE_PT_WATER = 273.16

#: 饱和水汽压查表的最低温度，单位为 K
SVP_T_MIN = 183.15

#: 饱和水汽压查表的最高温度，单位为 K
SVP_T_MAX = 338.25

#: 饱和水汽压查表的温度增量，单位为 K
SVP_T_INCREMENT = 0.1


# ---------------------------------------------------------------------------
# 网格输入校验
# ---------------------------------------------------------------------------

_MEB_VALID_VAL = (-np.inf, np.inf, np.nan)


def _prepare_meb_inputs(
    temperature: Union[xr.DataArray, np.ndarray],
    wind_speed: Union[xr.DataArray, np.ndarray],
    relative_humidity: Union[xr.DataArray, np.ndarray],
    pressure: Union[xr.DataArray, np.ndarray],
) -> Optional[xr.DataArray]:
    """规范化四路输入并校验与温度场的坐标一致性，返回温度场模板。"""
    if isinstance(temperature, xr.DataArray):
        t_template = meb.checkout_griddata(temperature, valid_val=_MEB_VALID_VAL)
    else:
        t_template = None

    if t_template is not None:
        for label, field in (
            ("风速场", wind_speed),
            ("相对湿度场", relative_humidity),
            ("气压场", pressure),
        ):
            if isinstance(field, xr.DataArray):
                field_template = meb.checkout_griddata(field, valid_val=_MEB_VALID_VAL)
                if not meb.checkout_griddata_same_coords(
                    [t_template, field_template], is_time_match=True
                ):
                    raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    return t_template


# ---------------------------------------------------------------------------
# 饱和水汽压（显温计算辅助）
# ---------------------------------------------------------------------------

def _svp_pure_water_goff_gratch(temperature: np.ndarray) -> np.ndarray:
    """使用 Goff-Gratch 公式计算纯水系统中的饱和水汽压。

    参数
    ----------
    temperature : np.ndarray
        气温，单位为 K。

    返回
    -------
    np.ndarray
        饱和水汽压，单位为 hPa。
    """
    t = temperature.astype(np.float32, copy=False)
    triple_pt = np.float32(TRIPLE_PT_WATER)
    c1 = np.float32(10.79574)
    c2 = np.float32(5.028)
    c3 = np.float32(1.50475e-4)
    c4 = np.float32(-8.2969)
    c5 = np.float32(0.42873e-3)
    c6 = np.float32(4.76955)
    c7 = np.float32(0.78614)
    c8 = np.float32(-9.09685)
    c9 = np.float32(3.56654)
    c10 = np.float32(0.87682)
    c11 = np.float32(0.78614)

    over_triple = t > triple_pt  # 三相点以上用液态水公式，以下用冰面公式

    # 液态水饱和水汽压（Goff-Gratch，log10 形式）
    n0_w = c1 * (1.0 - triple_pt / t)
    n1_w = c2 * np.log10(t / triple_pt)
    n2_w = c3 * (1.0 - np.power(10.0, (c4 * (t / triple_pt - 1.0))))
    n3_w = c5 * (np.power(10.0, (c6 * (1.0 - triple_pt / t))) - 1.0)
    log_es_w = n0_w - n1_w + n2_w + n3_w + c7
    es_w = np.power(10.0, log_es_w)

    # 冰面饱和水汽压（低温分支）
    n0_i = c8 * ((triple_pt / t) - 1.0)
    n1_i = c9 * np.log10(triple_pt / t)
    n2_i = c10 * (1.0 - (t / triple_pt))
    log_es_i = n0_i - n1_i + n2_i + c11
    es_i = np.power(10.0, log_es_i)

    return np.where(over_triple, es_w, es_i).astype(np.float32)  # 按格点逐元素选分支


@functools.lru_cache(maxsize=1)
def _svp_table() -> tuple[float, ...]:
    """构建饱和水汽压查找表。"""
    svp_data = []
    temperatures = np.arange(
        SVP_T_MIN, SVP_T_MAX + 0.5 * SVP_T_INCREMENT, SVP_T_INCREMENT, dtype=np.float32
    )
    for temp in temperatures:
        svp_data.append(_svp_pure_water_goff_gratch(np.array([temp]))[0])
    # Goff-Gratch 结果为 hPa，查表统一存 Pa（×100）供后续插值
    return tuple(float(value * 100.0) for value in svp_data)


def _svp_from_lookup(temperature: np.ndarray) -> np.ndarray:
    """从查找表中插值得到纯水系统中的饱和水汽压。

    参数
    ----------
    temperature : np.ndarray
        气温，单位为 K。

    返回
    -------
    np.ndarray
        饱和水汽压，单位为 Pa。
    """
    t_clipped = np.clip(temperature, SVP_T_MIN, SVP_T_MAX - SVP_T_INCREMENT)  # 避免插值越界

    # 将温度映射到查表索引，table_index 为下界，interpolation_factor 为区间内小数部分
    table_position = (t_clipped - SVP_T_MIN) / SVP_T_INCREMENT
    table_index = table_position.astype(int)
    interpolation_factor = table_position - table_index
    svp_table_data = np.array(_svp_table(), dtype=np.float32)
    # 相邻两档线性插值（支持任意形状的 temperature 数组）
    return (1.0 - interpolation_factor) * svp_table_data[
        table_index
    ] + interpolation_factor * svp_table_data[table_index + 1]


def _calculate_svp_in_air(temperature: np.ndarray, pressure: np.ndarray) -> np.ndarray:
    """计算空气中的饱和水汽压。

    参数
    ----------
    temperature : np.ndarray
        气温，单位为 K。
    pressure : np.ndarray
        气压，单位为 Pa。

    返回
    -------
    np.ndarray
        空气中的饱和水汽压，单位为 Pa。
    """
    svp = _svp_from_lookup(temperature)
    temp_c = temperature + ABSOLUTE_ZERO  # K -> ℃，用于气压订正项
    # 饱和水汽压随气压与温度的微弱订正（Gill, A4.7）
    correction = 1.0 + 1.0e-8 * pressure * (4.5 + 6.0e-4 * temp_c * temp_c)
    return svp * correction.astype(np.float32)
