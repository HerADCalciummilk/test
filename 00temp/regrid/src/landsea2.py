#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""新版最近邻/双线性重网格插件（含可选海陆感知）。"""

from __future__ import annotations

import numpy as np
import xarray as xr

import meteva_base as meb

from regrid.src.utils.bilinear import (
    adjust_for_surface_mismatch,
    apply_weights,
    basic_indexes,
    basic_weights,
)
from regrid.src.utils.grid import (
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
from regrid.src.utils.nearest import nearest_regrid, nearest_with_mask_regrid
from regrid.utils.base_plugin import PostProcessingPlugin

NEAREST = "nearest"
BILINEAR = "bilinear"
WITH_MASK = "-with-mask"
BILINEAR2 = f"{BILINEAR}-2"
NEAREST2 = f"{NEAREST}-2"
NEAREST_MASK2 = f"{NEAREST}{WITH_MASK}-2"
BILINEAR_MASK2 = f"{BILINEAR}{WITH_MASK}-2"
NUM_NEIGHBOURS = 4


class RegridWithLandSeaMask(PostProcessingPlugin):
    """最近邻与双线性重网格，可选海陆掩码感知。

    考虑海陆掩码时，地表类型不匹配的源点不参与目标点插值。
    本类 ``regrid_mode`` 可选：``nearest-2``、``nearest-with-mask-2``、
    ``bilinear-2``、``bilinear-with-mask-2``。
    """

    def __init__(
        self, regrid_mode: str = "bilinear-2", vicinity_radius: float = 25000.0
    ):
        """
        初始化类。

        参数
        ----------
        regrid_mode :
            重网格插值模式。可选 ``bilinear-2``、``nearest-2``、
            ``nearest-with-mask-2``、``bilinear-with-mask-2``。
            后两者会按海陆类型调整重网格结果。
        vicinity_radius :
            搜索海岸线的邻域半径，单位米。
        """
        self.regrid_mode = regrid_mode
        self.vicinity = vicinity_radius

    def process(
        self,
        data_in: xr.DataArray,
        data_in_mask: xr.DataArray | None,
        data_out_mask: xr.DataArray,
    ) -> xr.DataArray:
        """
        考虑海陆掩码的重网格。

        ``data_in`` 须为经纬度规则网格；``data_in_mask`` 与 ``data_in`` 可为不同
        分辨率；``data_out_mask`` 可为经纬度规则网格或投影网格。落在 ``data_in``
        域外的目标点将被置为缺测（NaN）。

        参数
        ----------
        data_in :
            待重网格的场。
        data_in_mask :
            源网格 ``land_binary_mask``（陆=1，海=0），用于判断源模式数据的
            海陆归属；无掩码模式可为 ``None``。
        data_out_mask :
            目标网格 ``land_binary_mask``（陆=1，海=0）。

        返回
        -------
        xr.DataArray
            重网格结果。
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

        # 保证空间坐标升序，便于等间距与索引计算
        data_in = ensure_ascending_coord(data_in)
        if WITH_MASK in self.regrid_mode:
            data_in_mask = ensure_ascending_coord(data_in_mask)

        lat_spacing, lon_spacing = calculate_input_grid_spacing(data_in)

        # 目标点转为经纬对（经纬直接取坐标；投影则按 grid_mapping_attrs 转换）
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
