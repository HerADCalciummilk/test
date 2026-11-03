# -*- coding: utf-8 -*-
"""降水外推：按光流风场做半拉格朗日平流。"""
import math
import numpy as np
from utils.types import ScatterData, GridData
from proc.frequency_match import FrequencyMatch


class RainExtrapolation:
    """沿 \(u,v\) 将降水场回溯到出发位置并双线性取样。"""

    @staticmethod
    def simple_semi_lagrangian_in_angle(gd_u_wnd, gd_v_wnd, gd_rain, deta_time):
        """半拉格朗日平流（向量化）：出发点 \((λ-u\\Delta t,\\,φ-v\\Delta t)\)，越界保留原点。"""
        gd_output = gd_rain.copy_grid_data()
        yn, xn = gd_output.yn, gd_output.xn

        # Compute departure points for ALL grid points at once
        lon_grid = gd_output._lon  # (xn,) numpy array
        lat_grid = gd_output._lat  # (yn,) numpy array

        # Broadcast: departure_lon[j,i] = lon[i] - u[j,i] * dt
        departure_lon = lon_grid[np.newaxis, :] - gd_u_wnd.val * deta_time  # (yn, xn)
        departure_lat = lat_grid[:, np.newaxis] - gd_v_wnd.val * deta_time  # (yn, xn)

        # Compute fractional grid indices (i0, i1 for lon; j0, j1 for lat)
        i0 = np.floor((departure_lon + 1e-05 - gd_output.lon_start) / gd_output.d_lon).astype(np.intp)
        j0 = np.floor((departure_lat + 1e-05 - gd_output.lat_start) / gd_output.d_lat).astype(np.intp)

        # Clamp to valid range
        i0_clamped = np.clip(i0, 0, xn - 2)
        j0_clamped = np.clip(j0, 0, yn - 2)
        i1 = i0_clamped + 1
        j1 = j0_clamped + 1

        # Fractional weights
        lon_frac = (departure_lon - lon_grid[i0_clamped]) / gd_output.d_lon
        lat_frac = (departure_lat - lat_grid[j0_clamped]) / gd_output.d_lat

        # Bilinear interpolation: all vectorized
        # rain[j0, i0], rain[j0, i1], rain[j1, i0], rain[j1, i1]
        v00 = gd_rain.val[j0_clamped, i0_clamped]
        v01 = gd_rain.val[j0_clamped, i1]
        v10 = gd_rain.val[j1, i0_clamped]
        v11 = gd_rain.val[j1, i1]

        # Interpolate: (1-fx)*(1-fy)*v00 + fx*(1-fy)*v01 + (1-fx)*fy*v10 + fx*fy*v11
        w00 = (1.0 - lon_frac) * (1.0 - lat_frac)
        w01 = lon_frac * (1.0 - lat_frac)
        w10 = (1.0 - lon_frac) * lat_frac
        w11 = lon_frac * lat_frac

        interp_vals = w00 * v00 + w01 * v01 + w10 * v10 + w11 * v11

        # Where departure point is out of bounds, use original value
        out_of_bounds = (i0 < 0) | (i0 >= xn - 1) | (j0 < 0) | (j0 >= yn - 1)
        interp_vals[out_of_bounds] = gd_rain.val[out_of_bounds]

        gd_output.val = interp_vals
        return gd_output
