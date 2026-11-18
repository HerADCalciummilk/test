# -*- coding: utf-8 -*-
"""格点→格点海陆感知重网格（``InterpGgLandSea`` / ``AdjustLandSeaPoints``）。

接口：``InterpGgLandSea.process(data, target_grid, regridded_title=None)``。
无掩码模式走规则网格最近邻/双线性；``*-with-mask`` 在最近邻后再用
``AdjustLandSeaPoints`` 订正岸线附近类型错配；``*-2`` / ``*-with-mask-2``
委托 ``InterpGgLandSea2``。

算法要点
--------
1. ``bilinear`` / ``nearest``：``regrid_rectilinear`` 到目标网格。
2. ``nearest-with-mask``：先最近邻，再按源/目标 ``land_binary_mask`` 在邻域内
   用同类型最近源点替换错配格点。
3. ``*-2`` 族：权重/邻域与掩码在 ``InterpGgLandSea2`` 内一次完成。
4. 源域外行为由 ``extrapolation_mode``（``nan`` / ``extrapolate`` / ``error``）控制。
"""

from __future__ import annotations

import functools
import warnings
from typing import Optional, Tuple

import numpy as np
import xarray as xr

import meteva_base as meb
from numpy import ndarray
from scipy.spatial import cKDTree

from interp_gg_landsea2_plugin import InterpGgLandSea2
from utils._coords import distance_to_grid_cells, is_projected_spatial
from utils._vicinity import apply_threshold, maximum_within_vicinity
from utils.base_plugin import PostProcessingPlugin
from utils.grid import (
    grid_contains_cutout,
    normalize_extrapolation_mode,
    regrid_rectilinear,
)
from utils.meb_adapt import spatial_coords_match

MOSG_GRID_ATTRIBUTES = {"mosg__grid_type", "mosg__grid_version", "mosg__grid_domain"}
DEFAULT_TITLE = "unknown"


class InterpGgLandSea(PostProcessingPlugin):
    """最近邻 / 双线性重网格，可选海陆掩码感知。

    启用掩码时，地表类型不匹配的源点不参与目标点插值：陆点只取源陆、海点
    只取源海。无掩码的 ``bilinear`` / ``nearest`` 与带 ``-2`` 后缀的模式均可
    通过本类统一调度。

    Parameters
    ----------
    regrid_mode :
        ``bilinear``、``nearest``、``nearest-with-mask``、``bilinear-2``、
        ``nearest-2``、``nearest-with-mask-2``、``bilinear-with-mask-2``。
        含 ``*-with-mask*`` 时须提供 ``landmask``。
    extrapolation_mode :
        源域外填充：``nan``（默认）、``extrapolate``、``error``；
        历史别名 ``mask`` / ``nanmask`` 归一为 ``nan``。
    landmask :
        源网格 ``land_binary_mask``（陆=1，海=0）；掩码模式必需。
    landmask_vicinity :
        岸线邻域搜索半径（米），默认 ``25000``。
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
        extrapolation_mode: str = "nan",
        landmask: Optional[xr.DataArray] = None,
        landmask_vicinity: float = 25000,
    ):
        if regrid_mode not in self.REGRID_REQUIRES_LANDMASK:
            raise ValueError(f"Unrecognised regrid mode {regrid_mode}")
        if landmask is None and self.REGRID_REQUIRES_LANDMASK[regrid_mode]:
            raise ValueError(f"Regrid mode {regrid_mode} requires an input landmask")
        self.regrid_mode = regrid_mode
        self.extrapolation_mode = normalize_extrapolation_mode(extrapolation_mode)
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
        """按 ``regrid_mode`` 将 ``data`` 重网格到 ``target_grid``，并同步网格属性。"""
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

        elif regrid_mode in (
            "nearest-2",
            "nearest-with-mask-2",
            "bilinear-2",
            "bilinear-with-mask-2",
        ):
            result = InterpGgLandSea2(
                regrid_mode=regrid_mode, vicinity_radius=self.landmask_vicinity
            )(data, self.landmask_source_grid, target_grid)
        else:
            raise ValueError(f"Unrecognised regrid mode {regrid_mode}")

        attrs = dict(result.attrs)
        required_grid_attributes = [
            attr for attr in attrs if attr in MOSG_GRID_ATTRIBUTES
        ]
        for key in required_grid_attributes:
            if key in target_grid.attrs:
                attrs[key] = target_grid.attrs[key]
            else:
                attrs.pop(key, None)

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
        """将 ``data`` 重网格到 ``target_grid`` 的空间网格。

        Args:
            data: 待重网格的源场。
            target_grid: 目标网格模板；掩码模式下须含目标侧 ``land_binary_mask``。
            regridded_title: 写入结果 ``title`` 属性；缺省为 ``unknown``。

        Returns:
            重网格后的场（属性已按目标网格更新）。

        Raises:
            ValueError: 掩码模式下手源掩码空间范围不能覆盖 ``data``。
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
    """订正最近邻重网格后岸线附近的海陆类型错配。

    先将源掩码最近邻到目标网格，找出「目标类型 ≠ 所取源类型」且落在
    ``vicinity_radius`` 邻域内的格点，再替换为源网格上同类型最近邻值；
    邻域内无匹配点则保持原值。通常由 ``InterpGgLandSea`` 的
    ``nearest-with-mask`` 路径调用。

    Parameters
    ----------
    extrapolation_mode :
        源掩码重网格到目标网格时的域外行为（同 ``InterpGgLandSea``）。
    vicinity_radius :
        岸线邻域搜索半径（米），默认 ``25000``。
    """

    class _NoMatchesError(ValueError):
        """源掩码上不存在 ``selector_val`` 对应类型的格点。"""

    def __init__(
        self, extrapolation_mode: str = "nan", vicinity_radius: float = 25000.0
    ):
        self.input_land = None
        self.nearest_data = None
        self.output_land = None
        self.output_data = None
        self.extrapolation_mode = normalize_extrapolation_mode(extrapolation_mode)
        self.vicinity_radius = float(vicinity_radius)
        self._vicinity_grid_cells: Optional[int] = None

    @functools.lru_cache(maxsize=2)
    def _get_matches(
        self, selector_val: int
    ) -> Tuple[ndarray, ndarray, ndarray, ndarray]:
        """定位需订正的错配点，并建立「非本类型 → 本类型最近邻」索引。

        Returns:
            ``(mismatch_points, indices, use_points, no_use_points)``。
        """
        input_land_2d = np.asarray(self.input_land, dtype=np.float32)
        output_land_2d = np.asarray(self.output_land, dtype=np.float32)

        use_points = np.where(input_land_2d == selector_val)
        no_use_points = np.where(input_land_2d != selector_val)
        if use_points[0].size == 0:
            raise self._NoMatchesError

        tree = cKDTree(np.c_[use_points[0], use_points[1]])
        _, indices = tree.query(np.c_[no_use_points[0], no_use_points[1]])

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
        """对目标类型为 ``selector_val``（0=海 / 1=陆）的错配点就地订正。"""
        try:
            mismatch_points, indices, use_points, no_use_points = self._get_matches(
                selector_val
            )
        except self._NoMatchesError:
            return

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
        """订正已重网格到目标网格的场中岸线附近的海陆错配。

        Args:
            data: 已落在目标网格上的场（通常为最近邻结果）。
            input_land: 源网格海陆掩码。
            output_land: 目标网格海陆掩码（空间坐标须与 ``data`` 一致）。

        Returns:
            订正后的场；邻域内无同类型源点的格点保持原值。
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

        self.correct_where_input_true(0)
        self.correct_where_input_true(1)

        result = data.copy(deep=True)
        result.values = self.output_data.reshape(data.shape)
        return result
