#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""QPE 核心算法内部网格辅助。"""

from __future__ import annotations

from typing import Any, Mapping

import meteva_base as meb
import numpy as np
import xarray as xr

# meb 标准默认属性键；由 set_griddata_attrs 补齐，不从雷达输入整表拷贝。
_MEB_DEFAULT_ATTR_KEYS = frozenset(
    {
        "units",
        "model_var",
        "dtime_units",
        "level_type",
        "time_type",
        "time_bounds",
    }
)

# 降水产品可继承的观测溯源属性（不含 frequency 等雷达矩量固有属性）。
_PROVENANCE_ATTR_KEYS = (
    "site_code",
    "site_name",
    "site_longitude",
    "site_latitude",
    "site_alt_m",
    "scan_time",
    "data_name",
)


def rebuild_to_meb_griddata(
    values: np.ndarray,
    template: xr.DataArray,
    *,
    name: str,
    long_name: str,
    units: str = "mm/h",
    extra_attrs: Mapping[str, Any] | None = None,
) -> xr.DataArray:
    """按模板六维结构重组装降水率网格，并写入 meb 默认属性与方法属性。

    - 继承模板中的站点/时间等 provenance 属性；
    - 不继承 ``frequency`` 等雷达要素固有属性；
    - 用 ``set_griddata_attrs(..., is_default=True)`` 补齐 meb 默认属性；
    - ``units`` / ``name`` / ``long_name`` 及 ``extra_attrs`` 按产品与方法写入。
    """
    if not isinstance(template, xr.DataArray):
        raise TypeError("template must be an xarray.DataArray")

    normalized = meb.checkout_griddata(
        template,
        is_single=False,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    target_shape = tuple(
        int(normalized.sizes[dim])
        for dim in ("member", "level", "time", "dtime", "lat", "lon")
    )
    value_array = np.asarray(values, dtype=np.float32)
    if value_array.shape != target_shape:
        if value_array.size != int(np.prod(target_shape)):
            raise ValueError(
                f"values shape {value_array.shape} cannot reshape to {target_shape}"
            )
        value_array = value_array.reshape(target_shape)

    result = meb.grid_data(
        grid=meb.get_grid_of_data(normalized),
        data=value_array,
    )
    if result.dims != ("member", "level", "time", "dtime", "lat", "lon"):
        result = result.transpose(
            "member", "level", "time", "dtime", "lat", "lon"
        )

    inherited: dict[str, Any] = {}
    for key in _PROVENANCE_ATTR_KEYS:
        if key in normalized.attrs and key not in _MEB_DEFAULT_ATTR_KEYS:
            inherited[key] = normalized.attrs[key]
    result.attrs = inherited

    meb.set_griddata_attrs(
        result,
        units=units,
        model_var=None,
        dtime_units=None,
        level_type=None,
        time_type=None,
        time_bounds=None,
        is_default=True,
    )
    result.name = name
    result.attrs["long_name"] = long_name
    if extra_attrs:
        for key, value in extra_attrs.items():
            if value is None:
                continue
            # netCDF 不接受 Python bool；先转成 0/1。
            if isinstance(value, (bool, np.bool_)):
                value = int(value)
            result.attrs[key] = value
    return result
