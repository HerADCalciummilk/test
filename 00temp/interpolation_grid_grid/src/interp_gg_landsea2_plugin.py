# -*- coding: utf-8 -*-
"""格点→格点海陆感知重网格内核（``InterpGgLandSea2``，``*-2`` 模式）。

接口：``process(data_in, data_in_mask, data_out_mask)``。
由 ``InterpGgLandSea`` 在 ``nearest-2`` / ``bilinear-2`` /
``nearest-with-mask-2`` / ``bilinear-with-mask-2`` 下委托调用；也可单独使用。

算法要点
--------
1. 源场须为经纬度规则网格；目标可为经纬或投影网格（由 ``data_out_mask`` 定形）。
2. 先按目标外包络裁源域，再将目标点分为域内/域外；域外填 NaN。
3. 无掩码：四邻 ``nearest-2`` 或双线性 ``bilinear-2``。
4. 有掩码：四邻/双线性权重中剔除地表类型不匹配的源点，并在
   ``vicinity_radius`` 内搜索同类型邻点后重算。
5. ``data_in_mask`` 与 ``data_in`` 分辨率可以不同。
"""

from __future__ import annotations

import numpy as np
import xarray as xr

import meteva_base as meb

from utils.base_plugin import PostProcessingPlugin
from utils.bilinear import (
    adjust_for_surface_mismatch,
    apply_weights,
    basic_indexes,
    basic_weights,
)
from utils.grid import (
    calculate_input_grid_spacing,
    classify_input_surface_type,
    classify_output_surface_type,
    create_regrid_dataarray,
    ensure_ascending_coord,
    flatten_spatial_dimensions,
    group_target_points_with_source_domain,
    latlon_from_dataarray,
    mask_target_points_outside_source_domain,
    similar_surface_classify,
    slice_data_by_domain,
    slice_mask_data_by_domain,
    unflatten_spatial_dimensions,
)
from utils.nearest import nearest_regrid, nearest_with_mask_regrid

NEAREST = "nearest"
BILINEAR = "bilinear"
WITH_MASK = "-with-mask"
BILINEAR2 = f"{BILINEAR}-2"
NEAREST2 = f"{NEAREST}-2"
NEAREST_MASK2 = f"{NEAREST}{WITH_MASK}-2"
BILINEAR_MASK2 = f"{BILINEAR}{WITH_MASK}-2"
NUM_NEIGHBOURS = 4


class InterpGgLandSea2(PostProcessingPlugin):
    """``*-2`` 族最近邻 / 双线性重网格（可选海陆掩码）。

    与 ``InterpGgLandSea`` 的 ``bilinear`` / ``nearest`` / ``nearest-with-mask``
    不同，本类在一次遍历中完成邻点选取、权重与掩码订正，不经
    ``regrid_rectilinear`` + 后处理订正路径。

    Parameters
    ----------
    regrid_mode :
        ``bilinear-2``、``nearest-2``、``nearest-with-mask-2``、
        ``bilinear-with-mask-2``。后两者须提供 ``data_in_mask``。
    vicinity_radius :
        岸线邻域搜索半径（米），默认 ``25000``。
    """

    def __init__(
        self, regrid_mode: str = "bilinear-2", vicinity_radius: float = 25000.0
    ):
        self.regrid_mode = regrid_mode
        self.vicinity = vicinity_radius

    def process(
        self,
        data_in: xr.DataArray,
        data_in_mask: xr.DataArray | None,
        data_out_mask: xr.DataArray,
    ) -> xr.DataArray:
        """将 ``data_in`` 重网格到 ``data_out_mask`` 给出的目标网格。

        Args:
            data_in: 源场（经纬度规则网格）。
            data_in_mask: 源侧 ``land_binary_mask``（陆=1，海=0）；无掩码模式可为 ``None``。
            data_out_mask: 目标侧掩码/网格模板（经纬或投影均可）。

        Returns:
            重网格结果；源域外目标点为 NaN。

        Raises:
            ValueError: ``*-with-mask-2`` 未提供 ``data_in_mask``，或 ``regrid_mode`` 非法。
        """
        data_in = meb.checkout_griddata(data_in, valid_val=(-np.inf, np.inf, np.nan))
        data_out_mask = meb.checkout_griddata(
            data_out_mask, valid_val=(-np.inf, np.inf, np.nan)
        )
        if WITH_MASK in self.regrid_mode:
            if data_in_mask is None:
                raise ValueError(
                    f"Regrid mode {self.regrid_mode} requires an input landmask"
                )
            data_in_mask = meb.checkout_griddata(
                data_in_mask, valid_val=(-np.inf, np.inf, np.nan)
            )

        data_in = ensure_ascending_coord(data_in)
        if WITH_MASK in self.regrid_mode:
            data_in_mask = ensure_ascending_coord(data_in_mask)

        lat_spacing, lon_spacing = calculate_input_grid_spacing(data_in)
        out_latlons = latlon_from_dataarray(data_out_mask)

        total_out_point_num = out_latlons.shape[0]
        lat_max, lon_max = out_latlons.max(axis=0)
        lat_min, lon_min = out_latlons.min(axis=0)
        if WITH_MASK in self.regrid_mode:
            data_in, data_in_mask = slice_mask_data_by_domain(
                data_in, data_in_mask, (lat_max, lon_max, lat_min, lon_min)
            )
        else:
            data_in = slice_data_by_domain(
                data_in, (lat_max, lon_max, lat_min, lon_min)
            )

        outside_input_domain_index, inside_input_domain_index = (
            group_target_points_with_source_domain(data_in, out_latlons)
        )

        if len(outside_input_domain_index) > 0:
            out_latlons = out_latlons[inside_input_domain_index]

        in_latlons = latlon_from_dataarray(data_in)
        in_lons_size = int(data_in.sizes["lon"])

        in_values, lats_index, lons_index = flatten_spatial_dimensions(data_in)

        indexes = basic_indexes(
            out_latlons, in_latlons, in_lons_size, lat_spacing, lon_spacing
        )

        if WITH_MASK in self.regrid_mode:
            in_classified = classify_input_surface_type(data_in_mask, in_latlons)
            out_classified = classify_output_surface_type(data_out_mask)
            if len(outside_input_domain_index) > 0:
                out_classified = out_classified[inside_input_domain_index]
            surface_type_mask = similar_surface_classify(
                in_classified, out_classified, indexes
            )

        distances = np.zeros((out_latlons.shape[0], NUM_NEIGHBOURS), dtype=np.float32)
        weights = np.zeros((out_latlons.shape[0], NUM_NEIGHBOURS), dtype=np.float32)

        if NEAREST in self.regrid_mode:
            for i in range(NUM_NEIGHBOURS):
                distances[:, i] = np.square(
                    in_latlons[indexes[:, i], 0] - out_latlons[:, 0]
                ) + np.square(in_latlons[indexes[:, i], 1] - out_latlons[:, 1])

            if WITH_MASK in self.regrid_mode:
                distances, indexes = nearest_with_mask_regrid(
                    distances,
                    indexes,
                    surface_type_mask,
                    in_latlons,
                    out_latlons,
                    in_classified,
                    out_classified,
                    self.vicinity,
                )
            output_flat = nearest_regrid(distances, indexes, in_values)

        elif BILINEAR in self.regrid_mode:
            index_range = np.arange(weights.shape[0])
            weights[index_range] = basic_weights(
                index_range, indexes, out_latlons, in_latlons, lat_spacing, lon_spacing
            )

            if WITH_MASK in self.regrid_mode:
                weights, indexes = adjust_for_surface_mismatch(
                    in_latlons,
                    out_latlons,
                    in_classified,
                    out_classified,
                    weights,
                    indexes,
                    surface_type_mask,
                    in_lons_size,
                    self.vicinity,
                    lat_spacing,
                    lon_spacing,
                )
            output_flat = apply_weights(indexes, in_values, weights)
        else:
            raise ValueError(f"Unrecognised regrid mode {self.regrid_mode}")

        if len(outside_input_domain_index) > 0:
            output_flat = mask_target_points_outside_source_domain(
                total_out_point_num,
                outside_input_domain_index,
                inside_input_domain_index,
                output_flat,
            )

        output_array = unflatten_spatial_dimensions(
            output_flat, data_out_mask, in_values, lats_index, lons_index
        )
        return create_regrid_dataarray(output_array, data_in, data_out_mask)
