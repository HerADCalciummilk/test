#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形带折叠权重生成算法。

迁移自 IMPROVER ``improver.generate_ancillaries.generate_topographic_zone_weights``。
与 ``generate_ancillary.GenerateOrographyBandAncils``（地形带掩码）成对使用：
掩码标记格点所属带，本模块给出带间折叠权重。

算法面向双输入：
- ``xarray.DataArray``：即 meteva_base 六维网格（``member, level, time, dtime, lat, lon``），
  地形带映射到 ``level`` 维；
- ``numpy.ndarray``：纯数值数组。

核心数值计算不依赖空间坐标的物理数值。
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional, Sequence, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from cf_units import Unit as CfUnit
from numpy import ndarray
from numpy.ma.core import MaskedArray

from generate_ancillary.src.generate_ancillary import GenerateOrographyBandAncils
from generate_ancillary.src.utils._make_mask_griddata import make_mask_griddata
from generate_ancillary.utils.base_plugin import BasePlugin

__all__ = ["GenerateTopographicZoneWeights"]


class GenerateTopographicZoneWeights(BasePlugin):
    """生成地形带折叠权重辅助场。

    根据地形高度在各地形带中的位置计算权重：带中点权重为 1.0，带边界为 0.5；
    高于/低于中点的剩余权重 ``1 - w`` 分给相邻带，供下游按带折叠邻域结果时使用。
    若格点恰在带中心，则该带权重为 1.0；若在带边界，上下带各为 0.5；
    其余位置在中心与边界之间线性变化。

    输出格式：
    - DataArray（meteva_base 六维）：地形带映射到 ``level``；
      若提供海陆掩码，海点为 ``NaN``。
    - ``numpy``：形状 ``(n_band, y, x)``；若提供海陆掩码，返回 ``MaskedArray``。
    """

    def __repr__(self) -> str:
        return "<GenerateTopographicZoneWeights>"

    @staticmethod
    def add_weight_to_upper_adjacent_band(
        topographic_zone_weights: ndarray,
        orography_band: ndarray,
        midpoint: float,
        band_number: int,
        max_band_number: int,
    ) -> ndarray:
        """将高于中点的剩余权重写入上一带（或本带，若已是最高带）。"""
        weights = topographic_zone_weights[band_number]

        # 高于中点的格点：剩余权重给上一带
        # 带外为 NaN，比较会触发 invalid 警告，故忽略
        with np.errstate(invalid="ignore"):
            mask_y, mask_x = np.where(orography_band > midpoint)
        if band_number == max_band_number:
            adjacent_band_number = band_number
            topographic_zone_weights[adjacent_band_number, mask_y, mask_x] = 1.0
        else:
            adjacent_band_number = band_number + 1
            topographic_zone_weights[adjacent_band_number, mask_y, mask_x] = (
                1.0 - weights[mask_y, mask_x]
            )
        return topographic_zone_weights

    @staticmethod
    def add_weight_to_lower_adjacent_band(
        topographic_zone_weights: ndarray,
        orography_band: ndarray,
        midpoint: float,
        band_number: int,
    ) -> ndarray:
        """将低于中点的剩余权重写入下一带（或本带，若已是最低带）。"""
        weights = topographic_zone_weights[band_number]

        # 低于中点的格点：剩余权重给下一带
        # 带外为 NaN，比较会触发 invalid 警告，故忽略
        with np.errstate(invalid="ignore"):
            mask_y, mask_x = np.where(orography_band < midpoint)
        if band_number == 0:
            adjacent_band_number = band_number
            topographic_zone_weights[adjacent_band_number, mask_y, mask_x] = 1.0
        else:
            adjacent_band_number = band_number - 1
            topographic_zone_weights[adjacent_band_number, mask_y, mask_x] = (
                1.0 - weights[mask_y, mask_x]
            )
        return topographic_zone_weights

    @staticmethod
    def calculate_weights(points: ndarray, band: Sequence[float]) -> ndarray:
        """按带中点=1、边界=0.5 对高度做线性插值得到权重。"""
        weights = np.array([0.5, 1.0, 0.5], np.float32)
        midpoint = np.mean(band)
        band_points = np.array([band[0], midpoint, band[1]], np.float32)
        return np.interp(points, band_points, weights).astype(np.float32)

    @staticmethod
    def _squeeze_to_2d(values: ndarray, name: str) -> ndarray:
        """去掉长度为 1 的维后要求为二维空间场。"""
        arr = np.asarray(values)
        squeezed = np.squeeze(arr)
        if squeezed.ndim != 2:
            raise ValueError(
                f"{name} 在去掉长度为 1 的维后须为二维空间场，"
                f"当前 shape={arr.shape}"
            )
        return np.asarray(squeezed, dtype=np.float32)

    @staticmethod
    def _masked_or_nan(
        weights: ndarray, landmask_2d: Optional[ndarray], as_xarray: bool
    ) -> Union[ndarray, MaskedArray]:
        """按海陆掩码屏蔽海点：DataArray 路径用 NaN，numpy 路径用 MaskedArray。"""
        if landmask_2d is None:
            return np.asarray(weights, dtype=np.float32)

        # 权重路径 sea_fill_value=None → MaskedArray；掩码路径通常置 0
        band_plugin = GenerateOrographyBandAncils()
        masked_bands = [
            band_plugin.sea_mask(landmask_2d, weights[i], sea_fill_value=None)
            for i in range(weights.shape[0])
        ]
        stacked = np.ma.stack(masked_bands, axis=0)
        if as_xarray:
            # DataArray 不能直接挂 MaskedArray，海点填 NaN 供下游识别
            return np.asarray(stacked.filled(np.nan), dtype=np.float32)
        return stacked.astype(np.float32)

    def process(
        self,
        orography: Union[xr.DataArray, ndarray],
        thresholds_dict: Dict[str, Any],
        landmask: Optional[Union[xr.DataArray, ndarray]] = None,
    ) -> Union[xr.DataArray, ndarray, MaskedArray]:
        """按地形高度在各地形带内的位置计算折叠权重。

        Parameters
        ----------
        orography : xr.DataArray or ndarray
            标准网格上的地形高度场。DataArray 须为 meteva_base 六维且
            ``member/level/time/dtime`` 长度为 1；``ndarray`` 须为二维。
        thresholds_dict : dict
            所需地形带定义，须含：

            - ``bounds``：各地形带上下界列表，例如
              ``[[0, 50], [50, 200]]``；
            - ``units``：上下界单位字符串，例如 ``"m"``。

            完整示例::

                {"bounds": [[0, 50], [50, 200]], "units": "m"}

            未另行指定时，CLI 等入口可使用模块默认 ``THRESHOLDS_DICT``，形如::

                {
                    "bounds": [
                        [-500.0, 50.0], [50.0, 100.0], [100.0, 150.0],
                        [150.0, 200.0], [200.0, 250.0], [250.0, 300.0],
                        [300.0, 400.0], [400.0, 500.0], [500.0, 650.0],
                        [650.0, 800.0], [800.0, 950.0], [950.0, 6000.0],
                    ],
                    "units": "m",
                }

        landmask : xr.DataArray or ndarray or None, default=None
            标准网格海陆掩码，陆=1、海=0。若提供，则屏蔽海点
            （DataArray 路径为 NaN，numpy 路径为 MaskedArray）；
            若未提供，则对陆点与海点均按所属地形带生成权重。

        Returns
        -------
        xr.DataArray or ndarray or MaskedArray
            地形带权重场，表示各地形高度格点在各地形带中的权重贡献。
        """
        orography_is_xarray = isinstance(orography, xr.DataArray)

        if orography_is_xarray:
            unbounded = (-np.inf, np.inf, np.nan)
            orography = meb.checkout_griddata(orography,is_single=True, valid_val=unbounded)
            if isinstance(landmask, xr.DataArray):
                landmask = meb.checkout_griddata(landmask, valid_val=unbounded)

        if "bounds" not in thresholds_dict or not thresholds_dict["bounds"]:
            raise ValueError("未提供任何地形带阈值。")
        if "units" not in thresholds_dict:
            raise KeyError("thresholds_dict 缺少必需字段: units")

        target_units = (
            orography.attrs.get("units", "m") if orography_is_xarray else "m"
        )
        raw_bands = np.asarray(thresholds_dict["bounds"], dtype=np.float32)
        # 将阈值单位换算到地形场单位
        bands = CfUnit(thresholds_dict["units"]).convert(
            raw_bands, CfUnit(target_units)
        ).astype(np.float32)
        midpoints = np.mean(bands, axis=1).astype(np.float32)

        orog_values = (
            np.asarray(orography.values)
            if orography_is_xarray
            else np.asarray(orography)
        )
        # numpy 须为二维；六维 DataArray 可 squeeze 掉长度为 1 的维
        if orography_is_xarray:
            orog_2d = self._squeeze_to_2d(orog_values, "地形高度场")
        else:
            if orog_values.ndim != 2:
                raise ValueError(
                    "地形高度场须为二维数组，"
                    f"当前维度数={orog_values.ndim}，shape={orog_values.shape}"
                )
            orog_2d = np.asarray(orog_values, dtype=np.float32)

        landmask_2d: Optional[ndarray] = None
        if landmask is not None:
            if orography_is_xarray and isinstance(landmask, xr.DataArray):
                _, aligned = xr.broadcast(orography, landmask)
                land_values = np.asarray(aligned.values)
            elif isinstance(landmask, xr.DataArray):
                land_values = np.asarray(landmask.values)
            else:
                land_values = np.asarray(landmask)
            if orography_is_xarray:
                landmask_2d = self._squeeze_to_2d(land_values, "海陆掩码")
            else:
                if land_values.ndim != 2:
                    raise ValueError(
                        "海陆掩码须为二维数组，"
                        f"当前维度数={land_values.ndim}，shape={land_values.shape}"
                    )
                landmask_2d = np.asarray(land_values, dtype=np.float32)
            landmask_2d = GenerateOrographyBandAncils._broadcast_landmask_values(
                landmask_2d, tuple(orog_2d.shape)
            )

        if np.nanmax(orog_2d) > np.nanmax(bands):
            warnings.warn(
                "The maximum orography is greater than the uppermost band. "
                "This will potentially cause the topographic zone weights "
                "to not sum to 1 for a given grid point.",
                UserWarning,
                stacklevel=2,
            )
        if np.nanmin(orog_2d) < np.nanmin(bands):
            warnings.warn(
                "The minimum orography is lower than the lowest band. "
                "This will potentially cause the topographic zone weights "
                "to not sum to 1 for a given grid point.",
                UserWarning,
                stacklevel=2,
            )

        n_bands = bands.shape[0]
        weights = np.zeros((n_bands,) + orog_2d.shape, dtype=np.float32)
        max_band_number = n_bands - 1

        for band_number, band in enumerate(bands):
            # 落在当前带内的格点：lower < hgt <= upper
            mask_y, mask_x = np.where(
                (orog_2d > band[0]) & (orog_2d <= band[1])
            )
            # 带外先铺 NaN：邻带 np.where / interp 只作用带内点，避免带外被误写
            orography_band = np.full(orog_2d.shape, np.nan, dtype=np.float32)
            orography_band[mask_y, mask_x] = orog_2d[mask_y, mask_x]

            band_weights = self.calculate_weights(orography_band, band)
            weights[band_number, mask_y, mask_x] = band_weights[mask_y, mask_x]

            weights = self.add_weight_to_lower_adjacent_band(
                weights, orography_band, float(midpoints[band_number]), band_number
            )
            weights = self.add_weight_to_upper_adjacent_band(
                weights,
                orography_band,
                float(midpoints[band_number]),
                band_number,
                max_band_number,
            )

        sea_points_included = landmask_2d is None
        weights_out = self._masked_or_nan(
            weights, landmask_2d, as_xarray=orography_is_xarray
        )

        if orography_is_xarray:
            return make_mask_griddata(
                np.asarray(weights_out, dtype=np.float32),
                orography,
                bands,
                str(target_units),
                sea_points_included=sea_points_included,
                name="topographic_zone_weights",
                dtype=np.float32,
            )
        return weights_out
