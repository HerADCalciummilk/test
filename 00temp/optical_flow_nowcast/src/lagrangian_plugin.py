# -*- coding: utf-8 -*-
"""新增算法：度制半拉格朗日平流外推（rain24 原版 ``Lagrangian``）。

与既有 ``Extrapolation``（像素系半拉格朗日外推）并列独立，不改动旧实现。
"""
from __future__ import annotations

import meteva.base as meb
import numpy as np
import xarray as xr

from .base_plugin import BasePlugin


class Lagrangian(BasePlugin):
    @staticmethod
    def simple_semi_lagrangian_in_angle(
        gd_u_wnd: xr.DataArray,
        gd_v_wnd: xr.DataArray,
        gd_rain: xr.DataArray,
        delta_time,
    ):
        gd_output = gd_rain.copy()
        grid_info = meb.basicdata.get_grid_of_data(gd_output)
        delt_lon, delt_lat, lon_count, lat_count = (
            grid_info.dlon,
            grid_info.dlat,
            grid_info.nlon,
            grid_info.nlat,
        )
        start_lon, _, start_lat, _ = grid_info.slon, grid_info.elon, grid_info.slat, grid_info.elat

        u_array, v_array, tp_array = (
            gd_u_wnd.data.squeeze(),
            gd_v_wnd.data.squeeze(),
            gd_rain.data.squeeze(),
        )
        lon_array, lat_array = gd_output.lon.to_numpy(), gd_output.lat.to_numpy()

        lon_grid, lat_grid = np.meshgrid(lon_array, lat_array)

        lon_offset = lon_grid - u_array * delta_time
        lat_offset = lat_grid - v_array * delta_time

        index1 = np.clip(((lon_offset - start_lon) / delt_lon).astype(int), 0, lon_count - 2)
        index2 = np.clip(((lat_offset - start_lat) / delt_lat).astype(int), 0, lat_count - 2)

        lon1_weight = (lon_array[index1 + 1] - lon_offset) / delt_lon
        lon2_weight = (lon_offset - lon_array[index1]) / delt_lon
        lat1_weight = (lat_array[index2 + 1] - lat_offset) / delt_lat
        lat2_weight = (lat_offset - lat_array[index2]) / delt_lat

        tp_00 = tp_array[index2, index1]
        tp_01 = tp_array[index2, index1 + 1]
        tp_10 = tp_array[index2 + 1, index1]
        tp_11 = tp_array[index2 + 1, index1 + 1]
        correct_array = lon1_weight * (lat1_weight * tp_00 + lat2_weight * tp_10) + lon2_weight * (
            lat1_weight * tp_01 + lat2_weight * tp_11
        )

        gd_output.data = [[[[correct_array]]]]
        return gd_output

    def process(self, u, v, rain, delta_time=1.0):
        return self.simple_semi_lagrangian_in_angle(u, v, rain, delta_time)


__all__ = ["Lagrangian"]
