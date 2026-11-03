#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""海陆感知重网格插件"""

from __future__ import annotations

import functools
import warnings
from typing import Optional, Tuple

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray
from scipy.spatial import cKDTree

from regrid.src.landsea2 import RegridWithLandSeaMask
from regrid.src.utils._coords import distance_to_grid_cells, is_projected_spatial
from regrid.src.utils._vicinity import apply_threshold, maximum_within_vicinity
from regrid.src.utils.grid import regrid_rectilinear, grid_contains_cutout
from regrid.utils.base_plugin import PostProcessingPlugin
from regrid.utils.utils import spatial_coords_match

# 与上游 MOSG 网格属性集合保持一致，用于重网格后继承目标网格属性
MOSG_GRID_ATTRIBUTES = {"mosg__grid_type", "mosg__grid_version", "mosg__grid_domain"}
DEFAULT_TITLE = "unknown"


class RegridLandSea(PostProcessingPlugin):
    """最近邻与双线性重网格，可选海陆掩码感知。

    考虑海陆掩码时，地表类型不匹配的源点不参与目标点插值。例如在最近邻
    海陆感知模式下，重网格后的陆点总是取自源网格陆点，海点总是取自源网格
    海点。
    """

    REGRID_REQUIRES_LANDMASK = {
        "bilinear": False,
        "nearest": False,
        "nearest-with-mask": True,
        "nearest-2": False,
        "bilinear-2": False,
        "nearest-with-mask-2": True,
        "bilinear-with-mask-2": True,
    }

    def __init__(
        self,
        regrid_mode: str = "bilinear",
        extrapolation_mode: str = "nanmask",
        landmask: Optional[xr.DataArray] = None,
        landmask_vicinity: float = 25000,
    ):
        """
        初始化重网格参数。

        参数
        ----------
        regrid_mode :
            重网格插值模式。可选 ``bilinear``、``nearest``、
            ``nearest-with-mask``、``bilinear-2``、``nearest-2``、
            ``nearest-with-mask-2``、``bilinear-with-mask-2``。
            含 ``*-with-mask*`` 时会按海陆类型调整重网格结果。
        extrapolation_mode :
            源域外填充方式。可选 ``extrapolate``、``error``，以及
            ``nan`` / ``mask`` / ``nanmask``（三者等效，均填 NaN；默认
            ``nanmask``）。
        landmask :
            输入网格上的海陆掩码（``land_binary_mask``），陆点为 1、海点为 0；
            ``*-with-mask*`` 模式必需。
        landmask_vicinity :
            搜索海岸线的邻域半径，单位米。
        """
        if regrid_mode not in self.REGRID_REQUIRES_LANDMASK:
            raise ValueError(f"Unrecognised regrid mode {regrid_mode}")
        if landmask is None and self.REGRID_REQUIRES_LANDMASK[regrid_mode]:
            raise ValueError(f"Regrid mode {regrid_mode} requires an input landmask")
        self.regrid_mode = regrid_mode
        self.extrapolation_mode = extrapolation_mode
        self.landmask_source_grid = (
            meb.checkout_griddata(landmask, valid_val=(-np.inf, np.inf, np.nan))
            if landmask is not None
            else None
        )
        self.landmask_vicinity = None if landmask is None else landmask_vicinity
        self.landmask_name = "land_binary_mask"

    def _regrid_to_target(
        self,
        data: xr.DataArray,
        target_grid: xr.DataArray,
        regridded_title: Optional[str],
        regrid_mode: str,
    ) -> xr.DataArray:
        """将 ``data`` 重网格到 ``target_grid``，并更新属性。"""
        if regrid_mode in (
            "nearest-with-mask",
            "nearest-with-mask-2",
            "bilinear-with-mask-2",
        ):
            if self.landmask_source_grid is not None:
                src_name = self.landmask_source_grid.name or ""
                if self.landmask_name not in str(src_name):
                    warnings.warn(
                        f"Expected {self.landmask_name} in input_landmask "
                        f"but found {src_name!r}"
                    )
            tgt_name = target_grid.name or ""
            if self.landmask_name not in str(tgt_name):
                warnings.warn(
                    f"Expected {self.landmask_name} in target_grid but found {tgt_name!r}"
                )

        # (1) scipy 路径：bilinear / nearest / nearest-with-mask（对应原版 Iris Linear/Nearest）
        if regrid_mode in ("bilinear", "nearest", "nearest-with-mask"):
            method = "nearest" if "nearest" in regrid_mode else "linear"
            result = regrid_rectilinear(
                data, target_grid, method=method, extrapolation_mode=self.extrapolation_mode
            )
            if self.REGRID_REQUIRES_LANDMASK[regrid_mode]:
                result = AdjustLandSeaPoints(
                    vicinity_radius=self.landmask_vicinity,
                    extrapolation_mode=self.extrapolation_mode,
                )(result, self.landmask_source_grid, target_grid)

        # (2) 新版 *-2：nearest/bilinear ± 掩码
        elif regrid_mode in (
            "nearest-2",
            "nearest-with-mask-2",
            "bilinear-2",
            "bilinear-with-mask-2",
        ):
            result = RegridWithLandSeaMask(
                regrid_mode=regrid_mode, vicinity_radius=self.landmask_vicinity
            )(data, self.landmask_source_grid, target_grid)
        else:
            raise ValueError(f"Unrecognised regrid mode {regrid_mode}")

        # 继承目标网格的 MOSG 网格属性；缺失则删除源侧对应属性
        attrs = dict(result.attrs)
        required_grid_attributes = [
            attr for attr in attrs if attr in MOSG_GRID_ATTRIBUTES
        ]
        for key in required_grid_attributes:
            if key in target_grid.attrs:
                attrs[key] = target_grid.attrs[key]
            else:
                attrs.pop(key, None)

        # 目标为投影时，输出应带上目标投影参数
        if "grid_mapping_attrs" in target_grid.attrs:
            attrs["grid_mapping_attrs"] = target_grid.attrs["grid_mapping_attrs"]
        elif not is_projected_spatial(target_grid):
            attrs.pop("grid_mapping_attrs", None)

        attrs["title"] = DEFAULT_TITLE if regridded_title is None else regridded_title
        result.attrs = attrs
        return result

    def process(
        self,
        data: xr.DataArray,
        target_grid: xr.DataArray,
        regridded_title: Optional[str] = None,
    ) -> xr.DataArray:
        """
        将 ``data`` 重网格到 ``target_grid`` 给出的空间网格。

        参数
        ----------
        data :
            待重网格的场。
        target_grid :
            目标网格上的数据。若启用掩码重网格，该场应含用于订正的海陆掩码。
        regridded_title :
            重网格后写入的 ``title`` 属性；未指定时使用默认值。

        返回
        -------
        xr.DataArray
            重网格后的场，属性已更新。
        """
        data = meb.checkout_griddata(data, valid_val=(-np.inf, np.inf, np.nan))
        target_grid = meb.checkout_griddata(
            target_grid, valid_val=(-np.inf, np.inf, np.nan)
        )
        if self.REGRID_REQUIRES_LANDMASK[self.regrid_mode]:
            if not grid_contains_cutout(self.landmask_source_grid, data):
                raise ValueError("Source landmask does not match input grid")
        return self._regrid_to_target(
            data, target_grid, regridded_title, self.regrid_mode
        )


class AdjustLandSeaPoints(PostProcessingPlugin):
    """修正最近邻重网格后海陆类型不匹配的格点。

    当最近邻把目标点取到了与目标海陆类型相反的源点时，用源网格邻域内
    类型正确且最近的点替换；邻域内找不到匹配点则保持原值不变。
    """

    class _NoMatchesError(ValueError):
        """指定选择器在源掩码上无匹配点。"""

    def __init__(
        self, extrapolation_mode: str = "nanmask", vicinity_radius: float = 25000.0
    ):
        """
        初始化类。

        参数
        ----------
        extrapolation_mode :
            源域外填充方式。可选 ``extrapolate``、``error``，以及
            ``nan`` / ``mask`` / ``nanmask``（三者等效，均填 NaN；默认
            ``nanmask``）。
        vicinity_radius :
            搜索匹配海点或陆点的距离，单位米。
        """
        self.input_land = None
        self.nearest_data = None
        self.output_land = None
        self.output_data = None
        self.extrapolation_mode = extrapolation_mode
        self.vicinity_radius = float(vicinity_radius)
        self._vicinity_grid_cells: Optional[int] = None

    @functools.lru_cache(maxsize=2)
    def _get_matches(
        self, selector_val: int
    ) -> Tuple[ndarray, ndarray, ndarray, ndarray]:
        input_land_2d = np.asarray(self.input_land, dtype=np.float32)
        output_land_2d = np.asarray(self.output_land, dtype=np.float32)

        use_points = np.where(input_land_2d == selector_val)
        no_use_points = np.where(input_land_2d != selector_val)
        if use_points[0].size == 0:
            raise self._NoMatchesError

        # 用同类型点的最近邻填满全域，供后续 mismatch 替换取值
        tree = cKDTree(np.c_[use_points[0], use_points[1]])
        _, indices = tree.query(np.c_[no_use_points[0], no_use_points[1]])

        # 阈值 + vicinity max：标记“邻域内存在正确类型源点”的区域
        if selector_val > 0.5:
            thresholded = apply_threshold(
                input_land_2d, threshold_value=0.5, comparison_operator=">"
            )
        else:
            thresholded = apply_threshold(
                input_land_2d, threshold_value=0.5, comparison_operator="<="
            )
        in_vicinity = maximum_within_vicinity(
            thresholded, grid_point_radius=self._vicinity_grid_cells
        )

        mismatch_points = np.logical_and(
            np.logical_and(
                output_land_2d == selector_val,
                input_land_2d != selector_val,
            ),
            in_vicinity > 0.5,
        )
        return mismatch_points, indices, use_points, no_use_points

    def correct_where_input_true(self, selector_val: int) -> None:
        """就地修正 ``self.output_data`` 中类型不匹配的点。

        当 ``output_land`` 等于 ``selector_val``、但重网格后的 ``input_land``
        不等于该值，且邻域内存在匹配点时，用原始最近邻结果中最近的同类型点替换。

        参数
        ----------
        selector_val :
            需要订正的掩码取值。通常 ``1`` 表示订正近岸陆点，``0`` 表示订正近岸海点。
        """
        try:
            mismatch_points, indices, use_points, no_use_points = self._get_matches(
                selector_val
            )
        except self._NoMatchesError:
            return

        # nearest_data / output_data 形状为 (..., lat, lon)；按二维切片做同类型最近邻替换
        flat = self.nearest_data.reshape(-1, *self.nearest_data.shape[-2:])
        out_flat = self.output_data.reshape(-1, *self.output_data.shape[-2:])
        for i in range(flat.shape[0]):
            slice_data = np.array(flat[i], copy=True)
            slice_data[no_use_points] = slice_data[use_points][indices]
            out_flat[i][mismatch_points] = slice_data[mismatch_points]

    def process(
        self,
        data: xr.DataArray,
        input_land: xr.DataArray,
        output_land: xr.DataArray,
    ) -> xr.DataArray:
        """
        更新已重网格场，使目标海/陆点在邻域半径内尽量取自同类型源点。

        调用前须保证源侧海陆掩码已与源场网格核验一致。

        参数
        ----------
        data :
            待更新的场（与 ``output_land`` 同网格）。
        input_land :
            源网格上的 ``land_binary_mask``（陆=1，海=0），用于判断源模式数据的
            海陆归属；通常由最近邻方式投影到目标网格后再参与订正。
        output_land :
            目标网格上的 ``land_binary_mask``。

        返回
        -------
        xr.DataArray
            订正后的重网格结果。
        """
        data = meb.checkout_griddata(data, valid_val=(-np.inf, np.inf, np.nan))
        input_land = meb.checkout_griddata(
            input_land, valid_val=(-np.inf, np.inf, np.nan)
        )
        output_land = meb.checkout_griddata(
            output_land, valid_val=(-np.inf, np.inf, np.nan)
        )

        if not spatial_coords_match(data, output_land):
            raise ValueError(
                "X and Y coordinates do not match for data "
                f"{data.name!r} and {output_land.name!r}"
            )

        # 将源掩码最近邻重网格到目标网格
        regridded_input_land = regrid_rectilinear(
            input_land,
            output_land,
            method="nearest",
            extrapolation_mode=self.extrapolation_mode,
        )
        self.output_land = np.asarray(
            output_land.values.reshape(-1, *output_land.shape[-2:])[0], dtype=np.float32
        )
        self.input_land = np.asarray(
            regridded_input_land.values.reshape(-1, *regridded_input_land.shape[-2:])[0],
            dtype=np.float32,
        )
        self._vicinity_grid_cells = distance_to_grid_cells(
            output_land, self.vicinity_radius
        )

        self._get_matches.cache_clear()
        self.nearest_data = np.asarray(data.values, dtype=np.float32)
        self.output_data = np.array(self.nearest_data, copy=True)

        # 先修正误取陆地的海点，再修正误取海洋的陆点
        self.correct_where_input_true(0)
        self.correct_where_input_true(1)

        result = data.copy(deep=True)
        result.values = self.output_data.reshape(data.shape)
        return result
