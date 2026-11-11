#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""把高分辨率增强与模式增强的差，变成粗格块内总量守恒的降水调整。

本模块不改动 ``OrographicEnhancement`` 和 ``ApplyOrographicEnhancement``。
调用方仍用原方法分别算出两套增强场，并先插到与降水相同的网格。
核心实现都在 ``RedistributeOrographicEnhancement`` 类中：

1. 降水低于有雨阈值的格点不改，避免把干点加成雨。
2. 先对增强差做等权矩形平滑，半径以格点计，削弱细碎斑点。
3. 在边长为若干格点的粗格块内，只对有雨格点减去块内平均，使块内调整量之和为 0。
4. 若相加后出现负降水，截到 0，并把多出来的水量从该块内仍有雨的格点按当前降水量比例扣回。
5. 对订正后的降水做中心加权九点平滑，固定 2 次。

因此每个粗格块内有限值格点的降水之和与调整前一致。

效果说明（当前个例检验）
----------------
相对「先减后加」空报膨胀更轻，但仍是**负订正**：订正后 RMSE 高于订正前。
"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from scipy.ndimage import convolve, uniform_filter

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


class RedistributeOrographicEnhancement(BasePlugin):
    """用增强场之差重分配已有降水，按粗格块保持总量。

    当前为负订正方案：可抑制干区加雨，但订正后 RMSE 仍常高于订正前。

    参数
    ----------
    wet_threshold_mmh : float, 默认 0.1
        有雨阈值，单位 mm/h。低于该值的格点不参与重分配调整，但保留原值
        （不会因本参数被清零）。与 ``zero_below_mmh`` 独立。
    zero_below_mmh : float, 默认 0.1
        模式降水下限，单位 mm/h。``> 0`` 时：原始降水严格小于该值的格点先置 0，
        且不进入后续重分配。``0`` 表示关闭置零。湿点 demean 逻辑仍由
        ``wet_threshold_mmh`` 控制，保持不变。
    precip_spacing_km : float
        该次订正的降水格距，单位 km。ΔOE 等权窗半径由它和目标网格格距算出。
    model_orography_spacing_km : float
        该次订正的模式地形格距，单位 km。守恒块边长由它和目标网格格距算出。
    """

    _MEB_DIMS = ("member", "level", "time", "dtime", "lat", "lon")
    # 负降水截断后按比例扣回的轮数（实现细节，不对外暴露）
    _CLIP_ITERATIONS = 2
    # 订正后降水的中心加权九点次数。固定为 2，不对外暴露。
    _POST_SMOOTH_PASSES = 2
    # 经典气象九点：角 1、边 2、中心 4（和为 16）
    _CENTER_WEIGHT_3X3 = np.array(
        [[1.0, 2.0, 1.0], [2.0, 4.0, 2.0], [1.0, 2.0, 1.0]],
        dtype=np.float64,
    )

    @staticmethod
    def _ratio_cells(coarse_km: float, fine_km: float, *, minimum: int, label: str) -> int:
        """``round(粗格距 / 细格距)``，结果至少为 ``minimum``。"""
        if float(coarse_km) <= 0 or float(fine_km) <= 0:
            raise ValueError(f"{label}须为正，收到 {coarse_km}、{fine_km}")
        return max(int(minimum), int(round(float(coarse_km) / float(fine_km))))

    @staticmethod
    def doe_smooth_radius_cells(precip_spacing_km: float, target_spacing_km: float) -> int:
        """ΔOE 等权窗半径（目标网格格点）= round(降水格距 / 目标网格格距)。"""
        return RedistributeOrographicEnhancement._ratio_cells(
            precip_spacing_km,
            target_spacing_km,
            minimum=0,
            label="降水格距和目标网格格距",
        )

    @staticmethod
    def block_edge_cells(
        model_orography_spacing_km: float, target_spacing_km: float
    ) -> int:
        """守恒块边长（目标网格格点）= round(模式地形格距 / 目标网格格距)，至少 1 格。"""
        return RedistributeOrographicEnhancement._ratio_cells(
            model_orography_spacing_km,
            target_spacing_km,
            minimum=1,
            label="模式地形格距和目标网格格距",
        )

    def __init__(
        self,
        wet_threshold_mmh: float = 0.1,
        zero_below_mmh: float = 0.1,
        *,
        precip_spacing_km: float,
        model_orography_spacing_km: float,
    ) -> None:
        if wet_threshold_mmh < 0:
            raise ValueError(f"wet_threshold_mmh 须非负，收到 {wet_threshold_mmh}")
        if zero_below_mmh < 0:
            raise ValueError(f"zero_below_mmh 须非负，收到 {zero_below_mmh}")
        if float(precip_spacing_km) <= 0:
            raise ValueError(f"precip_spacing_km 须为正，收到 {precip_spacing_km}")
        if float(model_orography_spacing_km) <= 0:
            raise ValueError(
                f"model_orography_spacing_km 须为正，收到 {model_orography_spacing_km}"
            )
        self.wet_threshold_mmh = float(wet_threshold_mmh)
        self.zero_below_mmh = float(zero_below_mmh)
        self.precip_spacing_km = float(precip_spacing_km)
        self.model_orography_spacing_km = float(model_orography_spacing_km)

    def __repr__(self) -> str:
        return (
            "<RedistributeOrographicEnhancement: "
            f"wet_threshold_mmh={self.wet_threshold_mmh}, "
            f"zero_below_mmh={self.zero_below_mmh}, "
            f"precip_spacing_km={self.precip_spacing_km}, "
            f"model_orography_spacing_km={self.model_orography_spacing_km}>"
        )

    def process(
        self,
        precip: Union[xr.DataArray, np.ndarray],
        oe_high: Union[xr.DataArray, np.ndarray],
        oe_model: Union[xr.DataArray, np.ndarray],
    ) -> Tuple[Union[xr.DataArray, np.ndarray], Union[xr.DataArray, np.ndarray]]:
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
        corrected, adjustment
            与降水输入同型的场。``corrected`` 为重分配后再做中心加权九点平滑 2 次的订正降水；
            ``adjustment`` 为块内 demean 后的调整量（截断/再平衡与订正后平滑之前，
            即 ``平滑ΔOE − 块内均值``，干点为 0）。六维输入重组为标准六维网格，二维输入保持二维。

        异常
        ------
        ValueError
            空间形状不一致，或截断后已无降水可用来维持总量。
        """
        precip_values, precip_plane = self._spatial_plane(precip, "precip")
        high_values, _ = self._spatial_plane(oe_high, "oe_high")
        model_values, _ = self._spatial_plane(oe_model, "oe_model")
        if precip_values.shape != high_values.shape or precip_values.shape != model_values.shape:
            raise ValueError(
                "降水与两套增强场的空间形状须一致，"
                f"收到 precip {precip_values.shape}, oe_high {high_values.shape}, "
                f"oe_model {model_values.shape}"
            )

        precip_units = self._precip_units(precip)
        high_values = self._values_in_precip_units(oe_high, high_values, precip_units)
        model_values = self._values_in_precip_units(oe_model, model_values, precip_units)
        # 置零下限：小于阈值 → 0，且后续重分配看不到这些原毛毛雨
        if self.zero_below_mmh > 0:
            zero_thr = _threshold_in_units(precip_units, self.zero_below_mmh)
            precip_values = np.asarray(precip_values, dtype=np.float64, copy=True)
            tiny = np.isfinite(precip_values) & (precip_values < zero_thr)
            precip_values[tiny] = 0.0
        threshold = _threshold_in_units(precip_units, self.wet_threshold_mmh)
        if precip_plane is None:
            target_spacing_km = 1.0
        else:
            target_spacing_km = _estimate_grid_spacing_meters(precip_plane) / 1000.0
        corrected, adjustment = self._redistribute_precipitation(
            precip_values,
            high_values,
            model_values,
            wet_threshold=threshold,
            smooth_radius=self.doe_smooth_radius_cells(
                self.precip_spacing_km, target_spacing_km
            ),
            block_cells=self.block_edge_cells(
                self.model_orography_spacing_km, target_spacing_km
            ),
        )
        corrected = self._smooth_corrected_center9(corrected)
        corrected_out = self._restore_like_precip(precip, corrected, precip_units)
        adjustment_out = self._restore_like_precip(
            precip, adjustment.astype(np.float32, copy=False), precip_units
        )
        if isinstance(adjustment_out, xr.DataArray):
            adjustment_out.name = "precip_adjustment"
        return corrected_out, adjustment_out

    def compute_block_adjustment(
        self,
        precip: np.ndarray,
        oe_high: np.ndarray,
        oe_model: np.ndarray,
        *,
        wet_threshold: float,
        smooth_radius: int,
        block_cells: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """计算重分配用的增强差、平滑场与块内 demean 后的调整量（截断前）。

        输入可以是二维，或 meb 六维单场（前维长度为 1）；内部一律压到 lat/lon 二维。
        诊断用：调用方自行换好单位并传入半径、块边长。

        返回
        -------
        difference, smoothed, adjustment
            均为二维 float64；非可调格点上 adjustment 为 0。
        """
        _, difference, smoothed, adjustment, _ = self._block_fields(
            precip,
            oe_high,
            oe_model,
            wet_threshold=wet_threshold,
            smooth_radius=smooth_radius,
            block_cells=block_cells,
        )
        return difference, smoothed, adjustment

    def _redistribute_precipitation(
        self,
        precip: np.ndarray,
        oe_high: np.ndarray,
        oe_model: np.ndarray,
        *,
        wet_threshold: float,
        smooth_radius: int,
        block_cells: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """对二维降水场按粗格块做零和调整。

        返回
        -------
        balanced, adjustment
            ``balanced`` 为截断再平衡后的订正降水（float32）；
            ``adjustment`` 为块内 demean 后的调整量（float64，截断前）。
        """
        precip64, _, _, adjustment, adjustable = self._block_fields(
            precip,
            oe_high,
            oe_model,
            wet_threshold=wet_threshold,
            smooth_radius=smooth_radius,
            block_cells=block_cells,
        )
        finite = np.isfinite(precip64)
        updated = np.where(finite, precip64 + adjustment, np.nan)
        if np.any(adjustable):
            block_id = self._coarse_block_id(precip64.shape, block_cells)
            balanced = self._clip_and_rebalance_blocks(
                precip64,
                updated,
                finite,
                adjustable,
                block_id,
                self._CLIP_ITERATIONS,
            )
        else:
            balanced = np.where(finite, precip64, np.nan)
        return balanced.astype(np.float32), adjustment

    def _smooth_corrected_center9(self, values: np.ndarray) -> np.ndarray:
        """订正后降水做中心加权九点平滑，固定 ``_POST_SMOOTH_PASSES`` 次。

        核为角 1 / 边 2 / 中心 4。有限值（含 0）参与，NaN 不参与；每次后截到 ``>= 0``。
        """
        out = np.asarray(values, dtype=np.float64, copy=True)
        finite = np.isfinite(out)
        for _ in range(self._POST_SMOOTH_PASSES):
            smoothed = self._masked_weighted_mean(out, finite, self._CENTER_WEIGHT_3X3)
            out = np.where(finite, np.maximum(smoothed, 0.0), np.nan)
        return out.astype(np.float32)

    @staticmethod
    def _as_2d(arr: np.ndarray, name: str) -> np.ndarray:
        """压成 lat/lon 二维。允许 meb 六维单场（前四维长度为 1）。"""
        a = np.asarray(arr, dtype=np.float64)
        while a.ndim > 2 and a.shape[0] == 1:
            a = a[0]
        if a.ndim != 2:
            a = np.squeeze(a)
        if a.ndim != 2:
            raise ValueError(
                f"{name} 须为二维或可压成二维，收到 shape={np.asarray(arr).shape}"
            )
        return np.array(a, dtype=np.float64, copy=True)

    def _block_fields(
        self,
        precip: np.ndarray,
        oe_high: np.ndarray,
        oe_model: np.ndarray,
        *,
        wet_threshold: float,
        smooth_radius: int,
        block_cells: int,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """共享的块订正中间量：降水、增强差、平滑差、调整量、可调掩码。"""
        precip64 = self._as_2d(precip, "precip")
        high2d = self._as_2d(oe_high, "oe_high")
        model2d = self._as_2d(oe_model, "oe_model")
        if precip64.shape != high2d.shape or precip64.shape != model2d.shape:
            raise ValueError(
                "降水与两套增强场的空间形状须一致，"
                f"收到 precip {precip64.shape}, oe_high {high2d.shape}, "
                f"oe_model {model2d.shape}"
            )
        difference = high2d - model2d
        radius = int(smooth_radius)
        if radius >= 1:
            smoothed = self._masked_local_mean(
                difference, np.isfinite(difference), radius
            )
        else:
            smoothed = np.array(difference, dtype=np.float64, copy=True)
        finite = np.isfinite(precip64)
        adjustable = (
            finite
            & (precip64 >= wet_threshold)
            & np.isfinite(difference)
            & np.isfinite(smoothed)
        )
        adjustment = np.zeros(precip64.shape, dtype=np.float64)
        if np.any(adjustable):
            block_id = self._coarse_block_id(precip64.shape, block_cells)
            adjustment[adjustable] = self._block_demean(
                smoothed[adjustable], block_id[adjustable]
            )
        return precip64, difference, smoothed, adjustment, adjustable

    @staticmethod
    def _coarse_block_id(shape: tuple[int, int], block_cells: int) -> np.ndarray:
        """按格点边长分块，返回与场同形的块编号。"""
        n_rows, n_cols = shape
        edge = int(block_cells)
        rows = np.arange(n_rows, dtype=np.int64)[:, None] // edge
        cols = np.arange(n_cols, dtype=np.int64)[None, :] // edge
        n_col_blocks = int(cols.max()) + 1
        return rows * n_col_blocks + cols

    @staticmethod
    def _block_demean(values: np.ndarray, block_id: np.ndarray) -> np.ndarray:
        """减去各粗格块内平均值，向量化实现。"""
        n_blocks = int(block_id.max()) + 1
        counts = np.bincount(block_id, minlength=n_blocks)
        sums = np.bincount(block_id, weights=values, minlength=n_blocks)
        means = np.zeros(n_blocks, dtype=np.float64)
        np.divide(sums, counts, out=means, where=counts > 0)
        return values - means[block_id]

    @staticmethod
    def _masked_local_mean(
        values: np.ndarray, mask: np.ndarray, radius: int
    ) -> np.ndarray:
        """窗口内掩码格点的平均值。分子分母使用同一矩形窗。"""
        size = 2 * radius + 1
        filled = np.where(mask, values, 0.0).astype(np.float32, copy=False)
        weights = mask.astype(np.float32)
        summed = uniform_filter(filled, size=size, mode="constant", cval=0.0)
        counted = uniform_filter(weights, size=size, mode="constant", cval=0.0)
        mean = np.zeros(values.shape, dtype=np.float64)
        valid = counted > 0
        mean[valid] = np.asarray(summed, dtype=np.float64)[valid] / np.asarray(
            counted, dtype=np.float64
        )[valid]
        mean[~valid] = np.nan
        return mean

    @staticmethod
    def _masked_weighted_mean(
        values: np.ndarray,
        mask: np.ndarray,
        kernel: np.ndarray,
    ) -> np.ndarray:
        """掩码格点上的核加权平均；核与 mask 同时卷积作归一化。"""
        filled = np.where(mask, values, 0.0).astype(np.float64, copy=False)
        weights = mask.astype(np.float64)
        kern = np.asarray(kernel, dtype=np.float64)
        summed = convolve(filled, kern, mode="constant", cval=0.0)
        counted = convolve(weights, kern, mode="constant", cval=0.0)
        mean = np.full(values.shape, np.nan, dtype=np.float64)
        valid = counted > 0
        mean[valid] = summed[valid] / counted[valid]
        return mean

    @staticmethod
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
        target = np.bincount(
            block_id[finite], weights=precip[finite], minlength=n_blocks
        )

        for _ in range(iterations):
            negative = adjustable & (out < 0)
            if not np.any(negative):
                break
            deficit = np.bincount(
                block_id[negative], weights=-out[negative], minlength=n_blocks
            )
            out[negative] = 0.0
            donors = adjustable & (out > 0)
            if not np.any(donors):
                break
            donor_sum = np.bincount(
                block_id[donors], weights=out[donors], minlength=n_blocks
            )
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

    @classmethod
    def _spatial_plane(
        cls,
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
        if set(data.dims) == set(cls._MEB_DIMS):
            ordered = data.transpose(*cls._MEB_DIMS)
            for dim in cls._MEB_DIMS[:4]:
                if ordered.sizes[dim] != 1:
                    raise ValueError(
                        f"{name} 仅支持前四维长度均为 1 的六维单场；"
                        f"当前 {dim} 维长度为 {ordered.sizes[dim]}"
                    )
            plane = ordered.isel(
                member=0, level=0, time=0, dtime=0, drop=True
            ).transpose("lat", "lon")
            return np.asarray(plane.values), plane
        if data.ndim == 2:
            y_name, x_name = _get_spatial_coord_names(data)
            plane = data.transpose(y_name, x_name)
            return np.asarray(plane.values), plane
        raise ValueError(
            f"{name} 的 xarray 输入必须是标准六维网格 "
            "(member, level, time, dtime, lat, lon)，或已为二维空间场"
        )

    @staticmethod
    def _precip_units(precip: Union[xr.DataArray, np.ndarray]) -> str:
        if isinstance(precip, xr.DataArray):
            units = str(precip.attrs.get("units") or "").strip()
            if units:
                return units
        return "mm h-1"

    @classmethod
    def _values_in_precip_units(
        cls,
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
        converted_plane, _ = cls._spatial_plane(field.copy(data=converted), "oe")
        return converted_plane

    @classmethod
    def _restore_like_precip(
        cls,
        precip: Union[xr.DataArray, np.ndarray],
        values: np.ndarray,
        precip_units: str,
    ) -> Union[xr.DataArray, np.ndarray]:
        if isinstance(precip, np.ndarray):
            return values
        if set(precip.dims) == set(cls._MEB_DIMS):
            return rebuild_to_meb_griddata(
                values,
                precip,
                name=precip.name,
                units=precip_units,
            )
        y_name, x_name = _get_spatial_coord_names(precip)
        ordered = precip.transpose(y_name, x_name)
        restored = ordered.copy(data=values)
        restored.attrs = dict(ordered.attrs)
        restored.attrs["units"] = precip_units
        return restored


# 模块级别名，便于 CLI / notebook 在不实例化时直接取格距换算。
doe_smooth_radius_cells = RedistributeOrographicEnhancement.doe_smooth_radius_cells
block_edge_cells = RedistributeOrographicEnhancement.block_edge_cells
