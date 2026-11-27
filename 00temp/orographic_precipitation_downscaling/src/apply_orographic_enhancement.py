#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形增强叠加/扣除插件。

本模块实现了对降水场进行地形增强叠加或扣除的功能，是气象数据处理中地形效应修正的核心组件。
支持对单个或多个时次的降水数据进行处理，并可处理多时次的地形增强场匹配。

主要特性：
1. 支持 add（叠加）和 subtract（扣除）两种操作模式
2. 自动单位转换，确保降水场和地形增强场的单位一致
3. 时间匹配机制，可容差匹配最近的时次
4. 低降水阈值控制，避免在微量降水区域应用地形增强
5. 最小降水率保护，防止扣除后出现不合理的负值

注意：本实现基于 xarray DataArray 数据结构，针对标准六维网格数据格式设计。
"""

from __future__ import annotations

from typing import List, Sequence, Union

import numpy as np
import xarray as xr

import meteva_base as meb

from orographic_precipitation_downscaling.utils.base_plugin import BasePlugin
from orographic_precipitation_downscaling.utils.utils import convert_units
from orographic_precipitation_downscaling.src.utils._apply import (
    _extract_scalar_time_value,
    _nearest_time_index,
    _threshold_in_units,
    _to_datetime64,
)


class ApplyOrographicEnhancement(BasePlugin):
    """对降水场叠加或扣除地形增强项的插件类。

    该类实现了对降水场应用地形增强或扣除地形增强的核心算法。支持对单个或多个
    降水场进行处理，可处理多时次的地形增强场，并自动进行时间匹配、单位转换和
    质量保证检查。

    使用示例
    --------
    >>> plugin = ApplyOrographicEnhancement('add')
    >>> result = plugin.process(precip_data, oe_data)
    >>> 
    >>> # 或者使用可调用形式
    >>> plugin = ApplyOrographicEnhancement('subtract')
    >>> result = plugin(precip_data, oe_data)

    属性
    ----------
    min_precip_rate_mmh : float
        最小降水率阈值，默认 1.0/32.0 mm/h
    operation : str
        操作类型，'add' 表示叠加，'subtract' 表示扣除
    """

    def __init__(self, operation: str) -> None:
        """初始化地形增强插件。

        参数
        ----------
        operation : str
            运算类型，仅支持 'add' 或 'subtract'：
            - 'add'：将地形增强场叠加到降水场上
            - 'subtract'：从降水场中扣除地形增强场

        异常
        ------
        ValueError
            当 operation 不是 'add' 或 'subtract' 时抛出
        """
        self.min_precip_rate_mmh = 1.0 / 32.0
        self.operation = operation
        if self.operation not in {"add", "subtract"}:
            raise ValueError(
                "operation 仅支持 'add' 或 'subtract'，"
                f"收到: {self.operation!r}"
            )

    def __repr__(self) -> str:
        """返回对象的可读字符串表示。"""
        return f"<ApplyOrographicEnhancement: operation={self.operation}>"

    @staticmethod
    def _select_orographic_enhancement_data(
        precip_field: xr.DataArray,
        oe_field: xr.DataArray,
        allowed_time_diff: int = 1800,
    ) -> xr.DataArray:
        """根据降水场的时间选择匹配的地形增强场。

        参数
        ----------
        precip_field : xr.DataArray
            降水场数据
        oe_field : xr.DataArray
            地形增强场数据
        allowed_time_diff : int, 默认=1800
            允许的最大时间差（秒）

        返回
        -------
        xr.DataArray
            选择出的匹配地形增强场

        异常
        ------
        ValueError
            当无法匹配到合适的地形增强场时抛出
        """
        if "time" not in oe_field.dims:
            return oe_field
        if oe_field.sizes["time"] == 1:
            return oe_field.isel(time=0, drop=True)
        if "time" not in precip_field.coords:
            raise ValueError("地形增强场包含多时次时，降水输入必须包含 time 坐标")
        precip_time = _to_datetime64(
            _extract_scalar_time_value(precip_field.coords["time"].values)
        )
        if precip_time is None:
            raise ValueError("无法解析降水输入的 time 坐标")
        oe_times = oe_field.coords["time"].values
        index = _nearest_time_index(precip_time, np.asarray(oe_times), allowed_time_diff)
        return oe_field.isel(time=index, drop=True)

    def _apply_orographic_enhancement(
        self,
        precip_field: xr.DataArray,
        oe_field: xr.DataArray,
    ) -> xr.DataArray:
        """执行地形增强的叠加或扣除操作，并在低降水区域关闭增强项。

        参数
        ----------
        precip_field : xr.DataArray
            降水场数据
        oe_field : xr.DataArray
            地形增强场数据

        返回
        -------
        xr.DataArray
            处理后的降水场
        """
        precip_units = str(precip_field.attrs.get("units", "mm h-1"))
        if (oe_field.attrs.get("units") or "").strip():
            oe_values = convert_units(oe_field, precip_units)
        else:
            oe_values = np.asarray(oe_field.values, dtype=np.float32)
        threshold = _threshold_in_units(precip_units, self.min_precip_rate_mmh)
        precip_values = np.asarray(precip_field.values)
        with np.errstate(invalid="ignore"):
            oe_values = np.where(precip_values < threshold, 0.0, oe_values)
        if self.operation == "add":
            result_values = precip_values + oe_values
        else:
            result_values = precip_values - oe_values
        result = precip_field.copy(data=np.asarray(result_values, dtype=np.float32))
        result.attrs = dict(precip_field.attrs)
        result.attrs["units"] = precip_units
        return result

    def _apply_minimum_precip_rate(
        self,
        precip_field: xr.DataArray,
        updated_field: xr.DataArray,
    ) -> xr.DataArray:
        """在 subtract 模式下应用最小降水率阈值，防止结果过低。

        当从降水场中扣除地形增强时，确保结果不低于最小阈值。

        参数
        ----------
        precip_field : xr.DataArray
            原始降水场
        updated_field : xr.DataArray
            扣除后的降水场

        返回
        -------
        xr.DataArray
            应用最小降水率阈值后的降水场
        """
        if self.operation != "subtract":
            return updated_field
        units = str(updated_field.attrs.get("units", "mm h-1"))
        precip_units = str(precip_field.attrs.get("units", units))
        threshold = _threshold_in_units(units, self.min_precip_rate_mmh)
        threshold_in_precip = _threshold_in_units(
            precip_units, self.min_precip_rate_mmh
        )
        precip_values = np.asarray(precip_field.values)
        values = np.asarray(updated_field.values)
        with np.errstate(invalid="ignore"):
            mask = (precip_values >= threshold_in_precip) & (values <= threshold)
        new_values = np.where(mask, threshold, values)
        result = updated_field.copy(data=np.asarray(new_values, dtype=np.float32))
        result.attrs = dict(updated_field.attrs)
        result.attrs["units"] = units
        return result

    def process(
        self,
        precip_data: Union[xr.DataArray, Sequence[xr.DataArray]],
        orographic_enhancement_data: xr.DataArray,
        allowed_time_diff: int = 1800,
    ) -> Union[xr.DataArray, List[xr.DataArray]]:
        """对输入降水场应用地形增强操作的主处理方法。

        本方法是插件的核心入口，支持批量处理多个降水场。主要步骤包括：
        1. 数据格式验证和标准化
        2. 时间匹配和地形增强场选择
        3. 地形增强叠加/扣除运算
        4. 最小降水率阈值保护
        5. 结果验证和标准化

        参数
        ----------
        precip_data : Union[xr.DataArray, Sequence[xr.DataArray]]
            单个降水场，或降水场序列
        orographic_enhancement_data : xr.DataArray
            地形增强场，允许单时次或多时次（xarray time 维）输入
        allowed_time_diff : int, 默认=1800
            时间匹配容差（秒）

        返回
        -------
        Union[xr.DataArray, List[xr.DataArray]]
            若输入是单个场，返回单个处理结果；
            若输入是序列，返回对应结果列表。所有输出均为标准六维网格数据。

        异常
        ------
        TypeError
            当输入数据类型不正确时抛出
        ValueError
            当时间匹配失败或其他参数错误时抛出
        """
        if not isinstance(orographic_enhancement_data, xr.DataArray):
            raise TypeError("orographic_enhancement_data 必须为 xarray.DataArray")

        is_single_input = not isinstance(precip_data, (list, tuple))
        precip_items = (
            [precip_data] if is_single_input else list(precip_data)
        )
        oe_data_checked = meb.checkout_griddata(orographic_enhancement_data)

        updated: List[xr.DataArray] = []
        for precip_field in precip_items:
            if not isinstance(precip_field, xr.DataArray):
                raise TypeError("precip_data 中的每个元素都必须为 xarray.DataArray")
            precip_field = meb.checkout_griddata(precip_field)
            oe_field = self._select_orographic_enhancement_data(
                precip_field, oe_data_checked, allowed_time_diff
            )
            updated_field = self._apply_orographic_enhancement(precip_field, oe_field)
            updated_field = self._apply_minimum_precip_rate(precip_field, updated_field)
            updated_field = meb.checkout_griddata(updated_field)
            updated.append(updated_field)

        return updated[0] if is_single_input else updated
