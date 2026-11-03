#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""把高分辨率增强与模式增强的差，变成粗格块内总量守恒的降水调整。

本模块不改动 ``OrographicEnhancement`` 和 ``ApplyOrographicEnhancement``。
调用方仍用原方法分别算出两套增强场，并先插到与降水相同的网格。
这里只改变增强场施加到降水上的方式：

1. 降水低于有雨阈值的格点不改，避免把干点加成雨。
2. 先对增强差做公里尺度平滑，削弱 1 km 地形带来的细碎斑点。
3. 在预报降水尺度的粗格块内，只对有雨格点减去块内平均，使块内调整量之和为 0。
4. 若相加后出现负降水，截到 0，并把多出来的水量从该块内仍有雨的格点按当前降水量比例扣回。

因此每个粗格块内有限值格点的降水之和与调整前一致。
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import xarray as xr
from scipy.ndimage import uniform_filter

from orographic_precipitation_downscaling.src.utils._apply import _threshold_in_units
from orographic_precipitation_downscaling.src.utils._grid import (
    _estimate_grid_spacing_meters,
    _get_spatial_coord_names,
)
from orographic_precipitation_downscaling.utils.base_plugin import BasePlugin
from orographic_precipitation_downscaling.utils.utils import (
    convert_units,
    rebuild_to_meb_griddata,
)

_MEB_DIMS = ("member", "level", "time", "dtime", "lat", "lon")


class RedistributeOrographicEnhancement(BasePlugin):
    """用增强场之差重分配已有降水，按粗格块保持总量。

    参数
    ----------
    wet_threshold_mmh : float, 默认 0.1
        有雨阈值，单位 mm/h。低于该值的格点不参与调整。
    smooth_km : float, 默认 15
        增强差平滑窗口的半径，单位 km。小于一格时不做平滑。
    block_deg : float, 默认 0.1
        守恒分配的粗格边长，单位度，默认与预报降水网格一致。
        无经纬坐标时，按 ``block_deg × 111`` km 换算成格点数分块。
    grid_spacing_km : float, optional
        网格距，单位 km。缺省时由降水坐标估算；无坐标的数组按 1 km。
    clip_iterations : int, 默认 2
        负降水截断后按比例扣回的次数。
    window_km : float, optional
        兼容旧参数名，等同 ``smooth_km``。二者同时给出时以 ``smooth_km`` 为准。
    """

    def __init__(
        self,
        wet_threshold_mmh: float = 0.1,
        smooth_km: float = 15.0,
        block_deg: float = 0.1,
        grid_spacing_km: Optional[float] = None,
        clip_iterations: int = 2,
        window_km: Optional[float] = None,
    ) -> None:
        if wet_threshold_mmh < 0:
            raise ValueError(f"wet_threshold_mmh 须非负，收到 {wet_threshold_mmh}")
        if window_km is not None:
            if window_km < 0:
                raise ValueError(f"window_km 须非负，收到 {window_km}")
            if smooth_km == 15.0:
                smooth_km = float(window_km)
        if smooth_km < 0:
            raise ValueError(f"smooth_km 须非负，收到 {smooth_km}")
        if block_deg <= 0:
            raise ValueError(f"block_deg 须为正，收到 {block_deg}")
        if grid_spacing_km is not None and grid_spacing_km <= 0:
            raise ValueError(f"grid_spacing_km 须为正，收到 {grid_spacing_km}")
        if clip_iterations < 0:
            raise ValueError(f"clip_iterations 须非负，收到 {clip_iterations}")
        self.wet_threshold_mmh = float(wet_threshold_mmh)
        self.smooth_km = float(smooth_km)
        self.window_km = self.smooth_km
        self.block_deg = float(block_deg)
        self.grid_spacing_km = None if grid_spacing_km is None else float(grid_spacing_km)
        self.clip_iterations = int(clip_iterations)

    def __repr__(self) -> str:
        return (
            "<RedistributeOrographicEnhancement: "
            f"wet_threshold_mmh={self.wet_threshold_mmh}, "
            f"smooth_km={self.smooth_km}, "
            f"block_deg={self.block_deg}, "
            f"grid_spacing_km={self.grid_spacing_km}, "
            f"clip_iterations={self.clip_iterations}>"
        )

    def process(
        self,
        precip: Union[xr.DataArray, np.ndarray],
        oe_high: Union[xr.DataArray, np.ndarray],
        oe_model: Union[xr.DataArray, np.ndarray],
    ) -> Union[xr.DataArray, np.ndarray]:
        """在降水网格上按粗格块重分配增强差。

        参数
        ----------
        precip : xr.DataArray 或 np.ndarray
            订正前降水。须已落在目标网格上。
        oe_high : xr.DataArray 或 np.ndarray
            高分辨率地形上的增强场，网格与降水相同。
        oe_model : xr.DataArray 或 np.ndarray
            模式地形上的增强场，网格与降水相同。

        返回
        -------
        与降水输入同型的场。六维输入重组为标准六维网格，二维输入保持二维。

        异常
        ------
        ValueError
            空间形状不一致，或截断后已无降水可用来维持总量。
        """
        precip_values, precip_plane = _spatial_plane(precip, "precip")
        high_values, _ = _spatial_plane(oe_high, "oe_high")
        model_values, _ = _spatial_plane(oe_model, "oe_model")
        if precip_values.shape != high_values.shape or precip_values.shape != model_values.shape:
            raise ValueError(
                "降水与两套增强场的空间形状须一致，"
                f"收到 precip {precip_values.shape}, oe_high {high_values.shape}, "
                f"oe_model {model_values.shape}"
            )

        precip_units = _precip_units(precip)
        high_values = _values_in_precip_units(oe_high, high_values, precip_units)
        model_values = _values_in_precip_units(oe_model, model_values, precip_units)
        threshold = _threshold_in_units(precip_units, self.wet_threshold_mmh)
        spacing_km = self.grid_spacing_km
        if spacing_km is None:
            spacing_km = _spacing_km(precip_plane)
        corrected = redistribute_precipitation(
            precip_values,
            high_values,
            model_values,
            wet_threshold=threshold,
            smooth_km=self.smooth_km,
            block_deg=self.block_deg,
            grid_spacing_km=spacing_km,
            clip_iterations=self.clip_iterations,
            precip_plane=precip_plane,
        )
        return _restore_like_precip(precip, corrected, precip_units)


def redistribute_precipitation(
    precip: np.ndarray,
    oe_high: np.ndarray,
    oe_model: np.ndarray,
    *,
    wet_threshold: float,
    smooth_km: float,
    block_deg: float,
    grid_spacing_km: float,
    clip_iterations: int,
    precip_plane: Optional[xr.DataArray] = None,
) -> np.ndarray:
    """对二维降水场按粗格块做零和调整，返回 float32 结果。"""
    precip64 = np.asarray(precip, dtype=np.float64)
    difference = np.asarray(oe_high, dtype=np.float64) - np.asarray(oe_model, dtype=np.float64)
    finite = np.isfinite(precip64)
    adjustable = finite & (precip64 >= wet_threshold) & np.isfinite(difference)
    adjustment = np.zeros(precip64.shape, dtype=np.float64)
    if np.any(adjustable):
        radius = int(round(smooth_km / grid_spacing_km))
        if radius >= 1:
            smoothed = _masked_local_mean(difference, np.isfinite(difference), radius)
        else:
            smoothed = np.array(difference, dtype=np.float64, copy=True)
        block_id = _coarse_block_id(precip64.shape, block_deg, grid_spacing_km, precip_plane)
        adjustment[adjustable] = _block_demean(smoothed[adjustable], block_id[adjustable])

    updated = np.where(finite, precip64 + adjustment, np.nan)
    if np.any(adjustable):
        block_id = _coarse_block_id(precip64.shape, block_deg, grid_spacing_km, precip_plane)
        balanced = _clip_and_rebalance_blocks(
            precip64, updated, finite, adjustable, block_id, clip_iterations
        )
    else:
        balanced = _clip_and_rebalance(precip64, updated, finite, adjustable, clip_iterations)
    return balanced.astype(np.float32)


def _coarse_block_id(
    shape: tuple[int, int],
    block_deg: float,
    grid_spacing_km: float,
    precip_plane: Optional[xr.DataArray],
) -> np.ndarray:
    """按经纬粗格或格点分块，返回与场同形的块编号。"""
    n_rows, n_cols = shape
    if precip_plane is not None:
        y_name, x_name = _get_spatial_coord_names(precip_plane)
        lat = np.asarray(precip_plane.coords[y_name].values, dtype=np.float64)
        lon = np.asarray(precip_plane.coords[x_name].values, dtype=np.float64)
        if lat.size == n_rows and lon.size == n_cols:
            lat0 = float(np.nanmin(lat))
            lon0 = float(np.nanmin(lon))
            bi = np.floor((lat[:, None] - lat0) / block_deg).astype(np.int64)
            bj = np.floor((lon[None, :] - lon0) / block_deg).astype(np.int64)
            bi = bi - int(bi.min())
            bj = bj - int(bj.min())
            n_lon_blocks = int(bj.max()) + 1
            return bi * n_lon_blocks + bj

    block_km = block_deg * 111.0
    block_cells = max(1, int(round(block_km / grid_spacing_km)))
    rows = np.arange(n_rows, dtype=np.int64)[:, None] // block_cells
    cols = np.arange(n_cols, dtype=np.int64)[None, :] // block_cells
    n_col_blocks = int(cols.max()) + 1
    return rows * n_col_blocks + cols


def _block_demean(values: np.ndarray, block_id: np.ndarray) -> np.ndarray:
    """减去各粗格块内平均值，向量化实现。"""
    n_blocks = int(block_id.max()) + 1
    counts = np.bincount(block_id, minlength=n_blocks)
    sums = np.bincount(block_id, weights=values, minlength=n_blocks)
    means = np.zeros(n_blocks, dtype=np.float64)
    np.divide(sums, counts, out=means, where=counts > 0)
    return values - means[block_id]


def _masked_local_mean(values: np.ndarray, mask: np.ndarray, radius: int) -> np.ndarray:
    """窗口内掩码格点的平均值。分子分母使用同一矩形窗。"""
    size = 2 * radius + 1
    filled = np.where(mask, values, 0.0).astype(np.float32, copy=False)
    weights = mask.astype(np.float32)
    summed = uniform_filter(filled, size=size, mode="constant", cval=0.0)
    counted = uniform_filter(weights, size=size, mode="constant", cval=0.0)
    mean = np.zeros(values.shape, dtype=np.float64)
    valid = counted > 0
    mean[valid] = np.asarray(summed, dtype=np.float64)[valid] / np.asarray(counted, dtype=np.float64)[valid]
    mean[~valid] = np.nan
    return mean


def _clip_and_rebalance_blocks(
    precip: np.ndarray,
    updated: np.ndarray,
    finite: np.ndarray,
    adjustable: np.ndarray,
    block_id: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """逐粗格块截断负值并守恒扣回，用 bincount 向量化。"""
    out = np.array(updated, dtype=np.float64, copy=True)
    locked = finite & ~adjustable
    out[locked] = precip[locked]
    out[~finite] = np.nan
    if not np.any(finite):
        return out

    n_blocks = int(block_id.max()) + 1
    target = np.bincount(block_id[finite], weights=precip[finite], minlength=n_blocks)

    for _ in range(iterations):
        negative = adjustable & (out < 0)
        if not np.any(negative):
            break
        deficit = np.bincount(block_id[negative], weights=-out[negative], minlength=n_blocks)
        out[negative] = 0.0
        donors = adjustable & (out > 0)
        if not np.any(donors):
            break
        donor_sum = np.bincount(block_id[donors], weights=out[donors], minlength=n_blocks)
        factor = np.ones(n_blocks, dtype=np.float64)
        can = donor_sum > 0
        factor[can] = np.maximum(donor_sum[can] - deficit[can], 0.0) / donor_sum[can]
        out[donors] *= factor[block_id[donors]]

    current = np.bincount(
        block_id[finite],
        weights=np.where(finite, out, 0.0)[finite],
        minlength=n_blocks,
    )
    residual = current - target
    donors = adjustable & (out > 0)
    donor_sum = (
        np.bincount(block_id[donors], weights=out[donors], minlength=n_blocks)
        if np.any(donors)
        else np.zeros(n_blocks, dtype=np.float64)
    )
    need = np.abs(residual) > 1e-6
    if np.any(need):
        short = need & (donor_sum <= residual)
        if np.any(short):
            raise ValueError(
                "截断后的剩余降水不足以维持块内总量："
                f"不足块数 {int(short.sum())}"
            )
        factor = np.ones(n_blocks, dtype=np.float64)
        can = need & (donor_sum > 0)
        factor[can] = (donor_sum[can] - residual[can]) / donor_sum[can]
        if np.any(donors):
            out[donors] *= factor[block_id[donors]]
    return out


def _clip_and_rebalance(
    precip: np.ndarray,
    updated: np.ndarray,
    finite: np.ndarray,
    adjustable: np.ndarray,
    iterations: int,
) -> np.ndarray:
    """负值截到 0，并只从有雨格点按降水量比例扣回。"""
    block_id = np.zeros(precip.shape, dtype=np.int64)
    return _clip_and_rebalance_blocks(
        precip, updated, finite, adjustable, block_id, iterations
    )


def _spatial_plane(
    data: Union[xr.DataArray, np.ndarray],
    name: str,
) -> tuple[np.ndarray, Optional[xr.DataArray]]:
    """取出 lat/lon 二维数值，并保留带坐标的平面以便估算格距。"""
    if isinstance(data, np.ndarray):
        array = np.asarray(data)
        if array.ndim != 2:
            raise ValueError(f"{name} 的 numpy 输入必须是二维场")
        return array, None
    if not isinstance(data, xr.DataArray):
        raise TypeError(f"{name} 须为 xarray.DataArray 或 numpy.ndarray")
    if set(data.dims) == set(_MEB_DIMS):
        ordered = data.transpose(*_MEB_DIMS)
        for dim in _MEB_DIMS[:4]:
            if ordered.sizes[dim] != 1:
                raise ValueError(
                    f"{name} 仅支持前四维长度均为 1 的六维单场；"
                    f"当前 {dim} 维长度为 {ordered.sizes[dim]}"
                )
        plane = ordered.isel(member=0, level=0, time=0, dtime=0, drop=True).transpose("lat", "lon")
        return np.asarray(plane.values), plane
    if data.ndim == 2:
        y_name, x_name = _get_spatial_coord_names(data)
        plane = data.transpose(y_name, x_name)
        return np.asarray(plane.values), plane
    raise ValueError(
        f"{name} 的 xarray 输入必须是标准六维网格 "
        "(member, level, time, dtime, lat, lon)，或已为二维空间场"
    )


def _precip_units(precip: Union[xr.DataArray, np.ndarray]) -> str:
    if isinstance(precip, xr.DataArray):
        units = str(precip.attrs.get("units") or "").strip()
        if units:
            return units
    return "mm h-1"


def _values_in_precip_units(
    field: Union[xr.DataArray, np.ndarray],
    spatial_values: np.ndarray,
    precip_units: str,
) -> np.ndarray:
    """增强场换到降水单位。无单位时按数值已经是降水单位使用。"""
    if not isinstance(field, xr.DataArray):
        return spatial_values
    units = str(field.attrs.get("units") or "").strip()
    if not units or units == precip_units:
        return spatial_values
    converted = convert_units(field, precip_units)
    converted_plane, _ = _spatial_plane(
        field.copy(data=converted),
        "oe",
    )
    return converted_plane


def _spacing_km(plane: Optional[xr.DataArray]) -> float:
    if plane is None:
        return 1.0
    return _estimate_grid_spacing_meters(plane) / 1000.0


def _restore_like_precip(
    precip: Union[xr.DataArray, np.ndarray],
    values: np.ndarray,
    precip_units: str,
) -> Union[xr.DataArray, np.ndarray]:
    if isinstance(precip, np.ndarray):
        return values
    if set(precip.dims) == set(_MEB_DIMS):
        restored = rebuild_to_meb_griddata(
            values,
            precip,
            name=precip.name,
            units=precip_units,
        )
        return restored
    y_name, x_name = _get_spatial_coord_names(precip)
    ordered = precip.transpose(y_name, x_name)
    restored = ordered.copy(data=values)
    restored.attrs = dict(ordered.attrs)
    restored.attrs["units"] = precip_units
    return restored
    