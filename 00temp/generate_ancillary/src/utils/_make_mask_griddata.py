#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本包私有：由数组构造地形带掩码/权重的 meb 六维网格。

对应原库 ``improver.generate_ancillaries.generate_ancillary._make_mask_cube``：
新建网格对象，挂载空间坐标与地形带 ``level`` 坐标；不从输入整包拷贝业务属性。
仅透传 ``grid_mapping_attrs``，并用 ``meb.set_griddata_attrs`` 写入 meb 缺省字段
与硬编码 ``units="1"`` / ``level_type="altitude"``。
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import xarray as xr
from numpy import ndarray

import meteva_base as meb


def _coerce_bounds_2d(topographic_bounds: Sequence[float] | ndarray) -> ndarray:
    """校验并返回 shape ``(n_band, 2)`` 的 float32 边界。"""
    # 与原库一致：上下界均须给出，且不能为 None
    flat_check = np.asarray(topographic_bounds, dtype=object).ravel()
    if any(item is None for item in flat_check):
        raise TypeError(
            "topographic_bounds 的每个上下界均须给出；"
            f"当前为 {topographic_bounds}"
        )
    raw = np.asarray(topographic_bounds, dtype=np.float32)
    if raw.ndim == 1:
        if raw.size != 2:
            raise TypeError(
                "topographic_bounds 须恰好包含上下界两个值；"
                f"当前长度为 {raw.size}"
            )
        bounds = raw.reshape(1, 2)
    elif raw.ndim == 2 and raw.shape[1] == 2:
        bounds = raw
    else:
        raise TypeError(
            "topographic_bounds 须为 [lower, upper] 或 [[lower, upper], ...]；"
            f"当前形状为 {raw.shape}"
        )
    if not np.isfinite(bounds).all():
        raise TypeError(
            "topographic_bounds 的每个上下界均须为有限数值；"
            f"当前为 {topographic_bounds}"
        )
    return bounds


def make_mask_griddata(
    mask_data: ndarray,
    template: xr.DataArray,
    topographic_bounds: Sequence[float] | ndarray,
    topographic_units: str,
    *,
    sea_points_included: bool = False,
    name: str = "topography_mask",
    dtype=np.int32,
) -> xr.DataArray:
    """由掩码/权重数组新建 meb 六维 DataArray（对齐原库 ``_make_mask_cube``）。

    Parameters
    ----------
    mask_data :
        空间场 ``(y, x)``，或多带 ``(n_band, y, x)``。海点处理应在调用前完成
        （掩码路径填 0；权重 xarray 路径填 NaN）。
    template :
        提供 ``member/time/dtime/lat/lon`` 坐标；要求 ``level`` 长度为 1。
        仅借用坐标；attrs 仅透传 ``grid_mapping_attrs``。
    topographic_bounds :
        单带 ``[lower, upper]`` 或多带 ``[[lower, upper], ...]``。
    topographic_units :
        写入 ``level`` 坐标的单位（通常为地形高度单位）。
    sea_points_included :
        写入 ``topographic_zones_include_seapoints``。
    name :
        变量名。
    dtype :
        输出数据类型。
    """
    if not isinstance(template, xr.DataArray):
        raise TypeError("template 必须为 xarray.DataArray。")
    if template.sizes.get("level", 0) != 1:
        raise ValueError("地形带映射到 level 时要求模板 level 维长度为 1")

    bounds = _coerce_bounds_2d(topographic_bounds)
    n_band = bounds.shape[0]
    centers = np.mean(bounds, axis=1).astype(np.float32)

    values = np.asarray(mask_data, dtype=dtype)

    # 去掉与模板一致的单点 member/level/time/dtime，得到 (y,x) 或 (n_band,y,x)
    squeezed = np.squeeze(values)
    ny = int(template.sizes["lat"])
    nx = int(template.sizes["lon"])
    if squeezed.ndim == 2:
        if squeezed.shape != (ny, nx):
            raise ValueError(
                f"mask_data 空间形状 {squeezed.shape} 与模板 lat/lon "
                f"({ny}, {nx}) 不一致"
            )
        if n_band != 1:
            raise ValueError(
                f"二维 mask_data 仅对应单带，但 topographic_bounds 有 {n_band} 带"
            )
        spatial = squeezed[np.newaxis, ...]
    elif squeezed.ndim == 3:
        if squeezed.shape != (n_band, ny, nx):
            raise ValueError(
                f"mask_data 形状 {squeezed.shape} 须为 "
                f"(n_band={n_band}, lat={ny}, lon={nx})"
            )
        spatial = squeezed
    else:
        raise ValueError(
            f"mask_data 去掉长度为 1 的维后须为 2D 或 3D，当前 ndim={squeezed.ndim}"
        )

    # (n_band,y,x) -> (1,n_band,1,1,y,x)；member/time/dtime 取模板（长度均为 1）
    for dim in ("member", "time", "dtime"):
        if template.sizes.get(dim, 1) != 1:
            raise ValueError(
                f"当前要求模板 {dim} 维长度为 1，实际为 {template.sizes.get(dim)}"
            )

    data = spatial[np.newaxis, :, np.newaxis, np.newaxis, :, :]
    result = xr.DataArray(
        data,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": template.coords["member"],
            "level": xr.DataArray(
                centers,
                dims=("level",),
                attrs={"units": str(topographic_units)},
            ),
            "time": template.coords["time"],
            "dtime": template.coords["dtime"],
            "lat": template.coords["lat"],
            "lon": template.coords["lon"],
            "level_lower_bound": (("level",), np.asarray(bounds[:, 0], dtype=np.float32)),
            "level_upper_bound": (("level",), np.asarray(bounds[:, 1], dtype=np.float32)),
        },
        name=name,
    )
    result = result.transpose("member", "level", "time", "dtime", "lat", "lon")

    # 对齐原库：新建对象、少量自写属性；仅透传 CRS，其余用 meb 缺省
    new_attrs = {}
    gm = template.attrs.get("grid_mapping_attrs")
    if gm is not None:
        new_attrs["grid_mapping_attrs"] = gm
    result.attrs = new_attrs
    meb.set_griddata_attrs(
        result,
        units="1",
        # level 存放海拔分带，不能用 meb 默认 isobaric
        level_type="altitude",
        is_default=True,
    )
    result.attrs["topographic_zones_include_seapoints"] = str(bool(sea_points_included))
    result.name = name
    return result
