#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""meteva_base 网格数据适配工具。"""

from __future__ import annotations

import numpy as np
import xarray as xr

import meteva_base as meb

__all__ = [
    "rebuild_to_meb_griddata",
]

def rebuild_to_meb_griddata(
    values: np.ndarray,
    template: xr.DataArray,
    *,
    name: str | None = None,
    units: str | None = None,
    dtype=np.float32,
) -> xr.DataArray:
    """按 meteva_base 网格模板重组装输出结果。

    参数
    ----------
    values : np.ndarray
        待重组装的数值数组。
    template : xr.DataArray
        模板网格数据，用于继承维度顺序、坐标和属性信息。
    name : str, optional
        输出变量名；未指定时继承模板名。
    units : str, optional
        输出单位；未指定时使用 meb 默认空字符串，不继承模板单位。
    dtype : data-type, default=np.float32
        输出数据类型。

    返回
    -------
    xr.DataArray
        维度顺序为 ``member, level, time, dtime, lat, lon`` 的网格数据。
    """
    if not isinstance(template, xr.DataArray):
        raise TypeError("template 必须为 xarray.DataArray。")

    # 模板必须是完整六维网格，禁止自动补维。
    normalized = meb.checkout_griddata(template, valid_val=(-np.inf, np.inf, np.nan))

    target_shape = tuple(
        normalized.sizes[dim]
        for dim in ("member", "level", "time", "dtime", "lat", "lon")
    )
    value_array = np.asarray(values, dtype=dtype)
    if value_array.shape != target_shape:
        if value_array.size != int(np.prod(target_shape)):
            raise ValueError(
                f"values 形状 {value_array.shape} 无法重组为模板形状 {target_shape}。"
            )
        value_array = value_array.reshape(target_shape)

    # 通过 meteva_base 网格对象组装，避免手工补维和坐标构造误差。
    grid_info = meb.get_grid_of_data(normalized)
    result = meb.grid_data(grid=grid_info, data=value_array)

    if not isinstance(result, xr.DataArray):
        raise TypeError("meb.grid_data 返回结果不是 xarray.DataArray")
    if result.dims != ("member", "level", "time", "dtime", "lat", "lon"):
        result = result.transpose("member", "level", "time", "dtime", "lat", "lon")

    # 继承模板 attrs；缺省的 meb 标准属性由 set_griddata_attrs 补齐。
    result.attrs = dict(normalized.attrs)
    meb.set_griddata_attrs(
        result,
        units=units,
        model_var=result.attrs.get("model_var"),
        dtime_units=result.attrs.get("dtime_units"),
        level_type=result.attrs.get("level_type"),
        time_type=result.attrs.get("time_type"),
        time_bounds=result.attrs.get("time_bounds"),
        is_default=True,
    )
    result.name = name if name is not None else normalized.name
    return result

