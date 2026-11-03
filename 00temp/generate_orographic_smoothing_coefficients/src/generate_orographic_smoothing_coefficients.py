#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形梯度平滑系数生成算法。

根据地形相邻格点梯度生成递归滤波用的 x/y 平滑系数。
支持：
- 投影/距离坐标（`lat`/`lon` 的 units 可转换为米）；
- 经纬度球面格距（units 为度，或无 units。使用默认正球体半径做逐段 diff）。
"""

from __future__ import annotations

import operator
from typing import Optional, Union

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray

from generate_orographic_smoothing_coefficients.src.utils._gradient import (
    adjacent_gradients_projected,
)
from generate_orographic_smoothing_coefficients.utils.base_plugin import BasePlugin


class OrographicSmoothingCoefficients(BasePlugin):
    """
    基于地形梯度，为递归滤波生成平滑系数。

    平滑系数决定滤波时某一格点的新值中，有多少来自该格点自身、有多少来自滤波
    方向上的前一相邻格点。系数越大，来自邻点的比例越高，平滑越强。

    由地形梯度按用户给定幂次计算未归一化系数：

        未归一化系数 = |gradient| ** power

    再线性缩放到 ``min_gradient_smoothing_coefficient`` 与
    ``max_gradient_smoothing_coefficient`` 界定的区间。这两个上下限各自须满足
    ``0 <= value <= 0.5``。

    注意：输出网格在对应方向上比输入地形少一格（x 方向系数在 lon 上少 1，
    y 方向系数在 lat 上少 1）。这是因为系数同时用于递归滤波的正向与反向扫描，
    需要落在原网格相邻格点之间（中点），以利于守恒。

    本迁移实现额外约定：输入为 meb 六维单场；按 ``lat``/``lon`` 的 units 选择
    投影米制或经纬度球面路径计算相邻梯度；可选按 mask 在区域或边界处置零；
    返回两个六维 DataArray（x/y 方向）。
    """

    def __init__(
        self,
        min_gradient_smoothing_coefficient: float = 0.5,
        max_gradient_smoothing_coefficient: float = 0.0,
        power: float = 1,
        use_mask_boundary: bool = False,
        invert_mask: bool = False,
    ) -> None:
        """
        初始化插件。

        参数
        ----------
        min_gradient_smoothing_coefficient :
            地形梯度最小处使用的递归滤波平滑系数。一般应大于
            ``max_gradient_smoothing_coefficient``，以便在平坦地形上更强平滑。
            须满足 ``0 <= value <= 0.5``。
        max_gradient_smoothing_coefficient :
            地形梯度最大处使用的递归滤波平滑系数。一般应小于
            ``min_gradient_smoothing_coefficient``，以便在复杂地形上减弱平滑。
            须满足 ``0 <= value <= 0.5``。
        power :
            平滑系数公式中的幂次：未归一化系数 = ``|gradient| ** power``。
        use_mask_boundary :
            可向本插件传入掩码，用于指定将平滑系数置零（即不做平滑）的区域。
            为 ``True`` 时，不把整个掩码区域置零，而仅将掩码与非掩码过渡处的
            格点置零；主要用于避免跨海陆边界平滑。为 ``False`` 时，对掩码区域
            及边界对应的系数置零。仅在 ``process`` 传入 ``mask`` 时生效。
        invert_mask :
            默认（``False``）且 ``use_mask_boundary=False`` 时：掩码值为 1 的
            位置对应系数置零。设为 ``True`` 则反转语义，掩码值为 0 的位置置零。
            当 ``use_mask_boundary=True`` 时本选项无效。
        """
        for limit in (
            min_gradient_smoothing_coefficient,
            max_gradient_smoothing_coefficient,
        ):
            if limit < 0 or limit > 0.5:
                raise ValueError(
                    "min_gradient_smoothing_coefficient and max_gradient_smoothing_coefficient "
                    "must be 0 <= value <=0.5 to help ensure better conservation across the "
                    "whole field to which the recursive filter is applied. The values provided "
                    f"are {min_gradient_smoothing_coefficient} and "
                    f"{max_gradient_smoothing_coefficient} respectively"
                )

        self.max_gradient_smoothing_coefficient = np.float32(
            max_gradient_smoothing_coefficient
        )
        self.min_gradient_smoothing_coefficient = np.float32(
            min_gradient_smoothing_coefficient
        )
        self.power = power
        self.use_mask_boundary = use_mask_boundary
        self.mask_comparison = operator.le if invert_mask else operator.ge

    def __repr__(self) -> str:
        return (
            "<OrographicSmoothingCoefficients("
            f"min={self.min_gradient_smoothing_coefficient}, "
            f"max={self.max_gradient_smoothing_coefficient}, "
            f"power={self.power})>"
        )

    def scale_smoothing_coefficients(
        self, coeff_x: ndarray, coeff_y: ndarray
    ) -> tuple[ndarray, ndarray]:
        """将 x/y 系数共同缩放到 [min, max] 区间。"""
        cube_min = min(float(np.abs(coeff_x).min()), float(np.abs(coeff_y).min()))
        cube_max = max(float(np.abs(coeff_x).max()), float(np.abs(coeff_y).max()))
        span = cube_max - cube_min
        if span == 0:
            scaled_x = np.full_like(
                coeff_x, self.min_gradient_smoothing_coefficient, dtype=np.float32
            )
            scaled_y = np.full_like(
                coeff_y, self.min_gradient_smoothing_coefficient, dtype=np.float32
            )
            return scaled_x, scaled_y

        def _scale(values: ndarray) -> ndarray:
            scaled = (np.abs(values) - cube_min) / span
            scaled = (
                scaled
                * (
                    self.max_gradient_smoothing_coefficient
                    - self.min_gradient_smoothing_coefficient
                )
                + self.min_gradient_smoothing_coefficient
            )
            return scaled.astype(np.float32)

        return _scale(coeff_x), _scale(coeff_y)

    def unnormalised_smoothing_coefficients(self, gradient: ndarray) -> ndarray:
        """按幂次由梯度生成未归一化系数。"""
        return np.power(np.abs(gradient), self.power).astype(np.float32)

    def zero_masked(
        self,
        smoothing_coefficient_x: ndarray,
        smoothing_coefficient_y: ndarray,
        mask_2d: ndarray,
    ) -> None:
        """按 mask 在原位将系数置零。输入二维顺序为 (lat, lon)。"""
        mask_2d = np.asarray(mask_2d)
        if self.use_mask_boundary:
            zero_points_x = np.diff(mask_2d, axis=1) != 0
            zero_points_y = np.diff(mask_2d, axis=0) != 0
        else:
            zero_points_x = self.mask_comparison(mask_2d[:, :-1] + mask_2d[:, 1:], 1)
            zero_points_y = self.mask_comparison(mask_2d[:-1, :] + mask_2d[1:, :], 1)
        smoothing_coefficient_x[zero_points_x] = 0.0
        smoothing_coefficient_y[zero_points_y] = 0.0

    def _build_coefficient_dataarray(
        self,
        values_2d: ndarray,
        template: xr.DataArray,
        *,
        name: str,
        lat_values: ndarray,
        lon_values: ndarray,
    ) -> xr.DataArray:
        """将二维系数封装为六维 DataArray。"""
        values_6d = np.asarray(values_2d, dtype=np.float32)[
            np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :
        ]
        coords = {
            "member": template.coords["member"],
            "level": template.coords["level"],
            "time": template.coords["time"],
            "dtime": template.coords["dtime"],
            "lat": xr.DataArray(
                np.asarray(lat_values, dtype=np.float32),
                dims=("lat",),
                attrs=dict(template.coords["lat"].attrs),
            ),
            "lon": xr.DataArray(
                np.asarray(lon_values, dtype=np.float32),
                dims=("lon",),
                attrs=dict(template.coords["lon"].attrs),
            ),
        }
        attrs = dict(template.attrs)
        attrs["title"] = "Recursive filter smoothing coefficients"
        attrs.pop("history", None)
        attrs["power"] = self.power
        attrs["units"] = "1"
        return xr.DataArray(
            values_6d,
            dims=("member", "level", "time", "dtime", "lat", "lon"),
            coords=coords,
            attrs=attrs,
            name=name,
        )

    def process(
        self,
        orography: Union[xr.DataArray, ndarray],
        mask: Optional[Union[xr.DataArray, ndarray]] = None,
    ) -> tuple[xr.DataArray, xr.DataArray] | tuple[ndarray, ndarray]:
        """
        生成 x/y 方向平滑系数。

        参数：
        - orography: 地形场；xarray 路径要求六维单场。
        - mask: 可选掩码，空间网格须与地形一致。

        返回：
        - ``(smoothing_coefficient_x, smoothing_coefficient_y)``
          x 方向 lat 全长、lon 少 1；y 方向 lat 少 1、lon 全长。
        """
        if isinstance(orography, xr.DataArray):
            orography = meb.checkout_griddata(
                orography, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
            )
            values_2d = np.asarray(orography.values.squeeze(), dtype=np.float32)
            lat_values = np.asarray(orography.coords["lat"].values)
            lon_values = np.asarray(orography.coords["lon"].values)
            lat_units = orography.coords["lat"].attrs.get("units")
            lon_units = orography.coords["lon"].attrs.get("units")
        else:
            values_2d = np.asarray(orography, dtype=np.float32)
            if values_2d.ndim != 2:
                raise ValueError(
                    f"Expected orography on 2D grid, got {values_2d.ndim} dims"
                )
            raise ValueError(
                "numpy 输入缺少 lat/lon 坐标，请传入带坐标的六维 DataArray。"
            )

        if values_2d.ndim != 2:
            raise ValueError(
                f"Expected orography on 2D grid, got {values_2d.ndim} dims"
            )

        mask_2d = None
        if mask is not None:
            if isinstance(mask, xr.DataArray):
                mask = meb.checkout_griddata(
                    mask, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
                )
                if not np.array_equal(
                    mask.coords["lat"].values, orography.coords["lat"].values
                ) or not np.array_equal(
                    mask.coords["lon"].values, orography.coords["lon"].values
                ):
                    raise ValueError(
                        "If a mask is provided it must have the same grid as the "
                        "orography field."
                    )
                mask_2d = np.asarray(mask.values.squeeze())
            else:
                mask_2d = np.asarray(mask)
                if mask_2d.shape != values_2d.shape:
                    raise ValueError(
                        "If a mask is provided it must have the same grid as the "
                        "orography field."
                    )

        # 经纬业务场无 grid_mapping_attrs；球面半径用默认值（可在底层 API 显式传入）
        grad_x, grad_y, lon_mid_x, lat_mid_y = adjacent_gradients_projected(
            values_2d,
            lat_values,
            lon_values,
            lat_units=lat_units,
            lon_units=lon_units,
        )
        coeff_x = self.unnormalised_smoothing_coefficients(grad_x)
        coeff_y = self.unnormalised_smoothing_coefficients(grad_y)
        coeff_x, coeff_y = self.scale_smoothing_coefficients(coeff_x, coeff_y)

        if mask_2d is not None:
            self.zero_masked(coeff_x, coeff_y, mask_2d)

        result_x = self._build_coefficient_dataarray(
            coeff_x,
            orography,
            name="smoothing_coefficient_x",
            lat_values=lat_values,
            lon_values=lon_mid_x,
        )
        result_y = self._build_coefficient_dataarray(
            coeff_y,
            orography,
            name="smoothing_coefficient_y",
            lat_values=lat_mid_y,
            lon_values=lon_values,
        )
        # 空间坐标 attrs（含 units）从输入原样继承
        return result_x, result_y
