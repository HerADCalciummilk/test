#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形相关辅助场生成算法。

本模块实现了地形相关辅助场生成算法，包括地形带掩码生成和海陆掩码纠正。
地形带折叠权重见同目录 ``generate_topographic_zone_weights.py``。

算法面向双输入：
- ``xarray.DataArray``：即 meteva_base 六维网格（``member, level, time, dtime, lat, lon``）；
- ``numpy.ndarray``：纯数值数组。

算法不依赖空间坐标的物理数值进行计算，坐标仅参与 xarray 的维度对齐与广播，其值从未被读取或用于数值运算。因此：
- 输入场可以是任意空间坐标系（投影坐标 projection_x/y_coordinate 或地理坐标 lat/lon），不影响计算正确性。
- 若上游数据保留 grid_mapping 属性（如 lambert_azimuthal_equal_area 的投影参数），本模块会将其随输出场透传，供下游消费方按需重建 CRS 并做投影转换。

"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from cf_units import Unit as CfUnit
from numpy import ndarray
from numpy.ma.core import MaskedArray

from generate_ancillary.src.utils._make_mask_griddata import make_mask_griddata
from generate_ancillary.utils.base_plugin import BasePlugin

# 以下字典定义了默认的以米为单位的地形高度带（亦可作为 thresholds_dict 缺省配置）
THRESHOLDS_DICT = {
    "bounds": [
        [-500.0, 50.0],
        [50.0, 100.0],
        [100.0, 150.0],
        [150.0, 200.0],
        [200.0, 250.0],
        [250.0, 300.0],
        [300.0, 400.0],
        [400.0, 500.0],
        [500.0, 650.0],
        [650.0, 800.0],
        [800.0, 950.0],
        [950.0, 6000.0],
    ],
    "units": "m",
}

__all__ = [
    "THRESHOLDS_DICT",
    "CorrectLandSeaMask",
    "GenerateOrographyBandAncils",
]


class CorrectLandSeaMask(BasePlugin):
    """将海陆掩码纠正为 0/1 二值场。

    功能逻辑：
    插值后的海陆掩码场中，格点值为 0~1 之间的浮点数，表示该格点为陆地的概率。
    本方法以 0.5 为阈值进行二值化：
    - 格点值 < 0.5：判定为海，置为 0
    - 格点值 >= 0.5：判定为陆，置为 1
    输出为 int8 类型的二值掩码场。

    输入为 ``xarray.DataArray``（meteva_base 六维）时，输出同为六维 DataArray，
    维度与坐标保持不变；输入为 ``ndarray`` 时返回 ``ndarray``。
    """

    def __init__(self) -> None:
        pass

    def __repr__(self) -> str:
        """返回插件实例说明。"""
        return "<CorrectLandSeaMask>"

    @staticmethod
    def process(standard_landmask: Union[xr.DataArray, ndarray]) -> Union[xr.DataArray, ndarray]:
        """将插值后的海陆掩码阈值化为 0/1。

        以 0.5 为阈值对海陆掩码进行二值化，小于 0.5 置为 0（海），
        大于等于 0.5 置为 1（陆）。

        Parameters
        ----------
        standard_landmask : xr.DataArray or ndarray
            插值后的海陆掩码场，格点值为 0~1 之间的浮点数。

        Returns
        -------
        xr.DataArray or ndarray
            二值化后的海陆掩码场，取值含义为：0 表示海，1 表示陆，数据类型为 int8。
            输入为 xr.DataArray 时，返回 xr.DataArray，维度与坐标保持不变；
            输入为 ndarray 时，返回 ndarray。
        """
        if isinstance(standard_landmask, xr.DataArray):
            # DataArray 输入按 meteva_base 六维网格约定检查。
            unbounded = (-np.inf, np.inf, np.nan)
            standard_landmask = meb.checkout_griddata(
                standard_landmask, valid_val=unbounded
            )
            data = np.asarray(standard_landmask.values, dtype=np.float32).copy()
            data[data < 0.5] = 0
            data[data >= 0.5] = 1
            result = xr.DataArray(
                data.astype(np.int8),
                dims=standard_landmask.dims,
                coords=standard_landmask.coords,
                name="land_binary_mask",
            )
            # 对齐原库就地改名思路：仅透传 CRS，units 硬编码，其余走 meb 缺省
            new_attrs = {}
            gm = standard_landmask.attrs.get("grid_mapping_attrs")
            if gm is not None:
                new_attrs["grid_mapping_attrs"] = gm
            result.attrs = new_attrs
            meb.set_griddata_attrs(result, units="1", is_default=True)
            result.name = "land_binary_mask"
            return result

        data = np.asarray(standard_landmask, dtype=np.float32).copy()
        data[data < 0.5] = 0
        data[data >= 0.5] = 1
        return data.astype(np.int8)


class GenerateOrographyBandAncils(BasePlugin):
    """生成地形带掩码辅助场。

    按海拔阈值将地形高度场划分为多个连续地形带，每个带输出一张二值掩码
    （带内陆点为 1，其余为 0）。若提供海陆掩码，则每个带内海点置 0；
    若不提供，则陆海格点均参与分带。

    输出格式：
    - DataArray（meteva_base 六维）输入：返回同结构六维，地形带映射到 ``level``，
      ``level`` 长度为带数，坐标为带中心，并附带
      ``level_lower_bound`` / ``level_upper_bound``；
    - ndarray 输入：返回 ndarray，第一维为地形带索引。
    """

    def __repr__(self) -> str:
        """返回插件实例说明。"""
        return "<GenerateOrographyBandAncils>"

    @staticmethod
    def _coerce_threshold_bounds(topographic_bounds: Sequence[float]) -> ndarray:
        """校验并标准化地形带上下界。"""
        if any(item is None for item in topographic_bounds):
            msg = (
                "地形带阈值必须同时提供上下界："
                f"当前 topographic_bounds={topographic_bounds}"
            )
            raise TypeError(msg)
        if len(topographic_bounds) != 2:
            msg = (
                "地形带阈值只能包含上下两个界值："
                f"当前长度为 {len(topographic_bounds)}"
            )
            raise TypeError(msg)
        return np.asarray(topographic_bounds, dtype=np.float32)

    @staticmethod
    def _broadcast_landmask_values(
        landmask_values: ndarray, target_shape: tuple[int, ...]
    ) -> ndarray:
        """将 landmask 广播到与地形场一致的形状。"""
        if landmask_values.shape == target_shape:
            return landmask_values
        try:
            return np.broadcast_to(landmask_values, target_shape)
        except ValueError as exc:
            raise ValueError(
                "海陆掩码形状无法广播到地形场："
                f"{landmask_values.shape} -> {target_shape}"
            ) from exc

    @staticmethod
    def sea_mask(
        landmask: ndarray, orog_band: ndarray, sea_fill_value: Optional[int] = None
    ) -> Union[MaskedArray, ndarray]:
        """将海点从地形带结果中屏蔽或填固定值。

        根据海陆掩码，将海洋区域的格点屏蔽（设为 fill_value）或填充指定值。

        Parameters
        ----------
        landmask : ndarray
            海陆掩码，陆地格点为 1，海洋格点为 0。
        orog_band : ndarray
            地形带二值掩码。
        sea_fill_value : int or None, default=None
            海点的填充值。若为 None，则返回 masked array。

        Returns
        -------
        MaskedArray or ndarray
            海点处理后的地形带掩码。
            当 sea_fill_value 为 None 时，海点被屏蔽并返回 MaskedArray；
            当 sea_fill_value 为整数时，海点被填为该值并返回 ndarray。
        """
        # 找出海洋格点（landmask 为 False 的位置）
        points_to_mask = np.logical_not(landmask)

        if sea_fill_value is None:
            # 返回 masked array，海洋格点被屏蔽
            sea_fill_value = np.ma.default_fill_value(orog_band)
            orog_data = np.array(orog_band, copy=True)
            orog_data[points_to_mask] = sea_fill_value
            return np.ma.masked_array(orog_data, mask=points_to_mask)

        # 返回普通数组，海洋格点填入指定值
        mask_data = np.array(orog_band, copy=True)
        mask_data[points_to_mask] = sea_fill_value
        return mask_data

    def gen_orography_masks(
        self,
        standard_orography: Union[xr.DataArray, ndarray],
        standard_landmask: Optional[Union[xr.DataArray, ndarray]],
        thresholds: Sequence[float],
        units: str = "m",
    ) -> Union[xr.DataArray, ndarray]:
        """针对单个地形带生成掩码。

        功能逻辑：
        对单个地形带区间（如 [50, 100]），在地形高度场上标记所有满足
        lower < orog <= upper 的格点，生成二值掩码。
        若提供了海陆掩码，则将海洋格点置为 0。

        Parameters
        ----------
        standard_orography : xr.DataArray or ndarray
            地形高度场。
        standard_landmask : xr.DataArray or ndarray or None
            海陆掩码，可选。若提供，用于屏蔽海洋格点。
        thresholds : sequence of float
            地形带上下界，如 [lower, upper]。
        units : str, default="m"
            阈值的单位。

        Returns
        -------
        xr.DataArray or ndarray
            单个地形带的二值掩码。
            DataArray 输入时返回 meteva_base 六维，level 长度为 1；
            ndarray 输入时返回 ndarray，第一维长度为 1。
        """
        orography_is_xarray = isinstance(standard_orography, xr.DataArray)

        # 获取地形场的单位
        target_units = (
            standard_orography.attrs.get("units", "m")
            if orography_is_xarray
            else "m"
        )
        # 核心步骤1：单位换算，将阈值转换到地形场的单位
        threshold_values = np.asarray(thresholds, dtype=np.float32)
        converted_thresholds = CfUnit(units).convert(
            threshold_values, CfUnit(target_units)
        )
        lower_threshold, upper_threshold = converted_thresholds

        # 核心步骤2：阈值比较，生成二值掩码（lower < orog <= upper）
        orog_values = (
            np.asarray(standard_orography.values)
            if orography_is_xarray
            else np.asarray(standard_orography)
        )
        orog_band = (
            (orog_values > lower_threshold) & (orog_values <= upper_threshold)
        ).astype(np.int32)

        # 核心步骤3：海点处理，若提供了海陆掩码则将海洋格点置为 0
        if standard_landmask is not None:
            if orography_is_xarray and isinstance(standard_landmask, xr.DataArray):
                # 将海陆掩码广播到与地形场一致的形状
                _, aligned_landmask = xr.broadcast(standard_orography, standard_landmask)
                landmask_values = np.asarray(aligned_landmask.values)
            elif isinstance(standard_landmask, xr.DataArray):
                landmask_values = np.asarray(standard_landmask.values)
            else:
                landmask_values = np.asarray(standard_landmask)
            landmask_values = self._broadcast_landmask_values(
                landmask_values, tuple(orog_values.shape)
            )
            mask_data = self.sea_mask(landmask_values, orog_band, sea_fill_value=0)
            sea_points_included = False
        else:
            mask_data = orog_band
            sea_points_included = True

        # 核心步骤4：包装输出，将地形带映射到 level 维（对齐原库 _make_mask_cube）
        if orography_is_xarray:
            bounds = self._coerce_threshold_bounds(converted_thresholds)
            # level 坐标单位与换算后的阈值一致（即地形场单位）
            return make_mask_griddata(
                mask_data,
                standard_orography,
                bounds,
                str(target_units),
                sea_points_included=sea_points_included,
                name="topography_mask",
                dtype=np.int32,
            )

        return np.asarray(mask_data, dtype=np.int32)[np.newaxis, ...]

    def process(
        self,
        orography: Union[xr.DataArray, ndarray],
        thresholds_dict: Dict[str, Any],
        landmask: Optional[Union[xr.DataArray, ndarray]] = None,
    ) -> Union[xr.DataArray, ndarray]:
        """针对多个地形带循环生成掩码并堆叠输出。

        遍历 ``thresholds_dict["bounds"]`` 中每个地形带区间，调用
        ``gen_orography_masks`` 生成单带掩码，再沿 ``level`` 维（或数组第 0 轴）堆叠。

        Parameters
        ----------
        orography : xr.DataArray or ndarray
            标准网格上的地形高度场。DataArray 须为 meteva_base 六维网格。
        thresholds_dict : dict
            所需地形带定义，须含：

            - ``bounds``：各地形带上下界列表，例如
              ``[[0, 100], [100, 200]]``；
            - ``units``：上下界单位字符串，例如 ``"m"``。

            完整示例::

                {"bounds": [[0, 100], [100, 200]], "units": "m"}

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
            标准网格海陆掩码，陆=1、海=0。若提供，则每个带内海点置 0；
            若未提供，则陆海格点均参与分带。

        Returns
        -------
        xr.DataArray or ndarray
            地形带掩码场。
            DataArray 输入时返回 meteva_base 六维，``level`` 长度为地形带数量；
            ndarray 输入时返回 ndarray，第一维为地形带索引。
        """
        # 在入口统一做一次六维网格校验
        if isinstance(orography, xr.DataArray):
            unbounded = (-np.inf, np.inf, np.nan)
            orography = meb.checkout_griddata(orography, valid_val=unbounded)
            if isinstance(landmask, xr.DataArray):
                landmask = meb.checkout_griddata(landmask, valid_val=unbounded)

        # 校验阈值配置
        if "bounds" not in thresholds_dict or not thresholds_dict["bounds"]:
            raise ValueError("未提供任何地形带阈值。")
        if "units" not in thresholds_dict:
            raise KeyError("thresholds_dict 缺少必需字段: units")

        # 核心循环：遍历每个地形带区间，逐个生成掩码
        band_results = [
            self.gen_orography_masks(
                orography,
                landmask,
                limits,
                thresholds_dict["units"],
            )
            for limits in thresholds_dict["bounds"]
        ]

        if isinstance(orography, xr.DataArray):
            # 对齐原库：各带已由 make_mask_griddata 组装，此处仅沿 level 拼接
            result = xr.concat(band_results, dim="level")
            return result.transpose("member", "level", "time", "dtime", "lat", "lon")

        return np.concatenate([np.asarray(item) for item in band_results], axis=0)
