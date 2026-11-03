# -*- coding: utf-8 -*-
"""空间分析：双线性插值与降水 Cressman 逐步订正。"""
import math
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from utils.types import PointData, ScatterData, GridData


class SpatialAnalisis:
    """格点↔站点插值；多半径 Cressman（降水与通用两套）。"""
    @staticmethod
    def bilinear_interpolation(gd_background_data, sd_output, db_undef=0.0):
        """格点双线性插到站点；越界填 ``db_undef``。"""
        lons = np.array([pd.lon for pd in sd_output.sta_data], dtype=np.float64)
        lats = np.array([pd.lat for pd in sd_output.sta_data], dtype=np.float64)
        src_lon = gd_background_data._lon  # already numpy float64
        src_lat = gd_background_data._lat
        interp = RegularGridInterpolator(
            (src_lon, src_lat), gd_background_data.val.T,
            method='linear', bounds_error=False, fill_value=db_undef
        )
        pts = np.column_stack([lons, lats])
        vals = interp(pts)
        for i, pd in enumerate(sd_output.sta_data):
            pd.val = float(vals[i])

    @staticmethod
    def bilinear_interpolation_single_point(gd_background_data, pd_output, db_undef=0.0):
        num = int((pd_output.lon + 1e-05 - gd_background_data.lon_start) / gd_background_data.lon_interval)
        num2 = int((pd_output.lat + 1e-05 - gd_background_data.lat_start) / gd_background_data.lat_interval)
        if 0 <= num < gd_background_data.xn - 1 and 0 <= num2 < gd_background_data.yn - 1:
            v = gd_background_data.val
            num3 = (float(v[num, num2]) * (gd_background_data._lon[num + 1] - pd_output.lon) +
                    float(v[num + 1, num2]) * (pd_output.lon - gd_background_data._lon[num])) / gd_background_data.lon_interval
            num4 = (float(v[num, num2 + 1]) * (gd_background_data._lon[num + 1] - pd_output.lon) +
                    float(v[num + 1, num2 + 1]) * (pd_output.lon - gd_background_data._lon[num])) / gd_background_data.lon_interval
            val = (num3 * (gd_background_data._lat[num2 + 1] - pd_output.lat) +
                   num4 * (pd_output.lat - gd_background_data._lat[num2])) / gd_background_data.lat_interval
            pd_output.val = val
        else:
            pd_output.val = db_undef

    @staticmethod
    def _cressman_one_step_interpolation_for_rain(sd_input_data, gd_background_data, distance_limit,
                                                   number_limit=1.0, smooth=0.001, power_param=2.0, rain_limit=0.01):
        length = len(sd_input_data.sta_data)
        influence_grid = int(distance_limit / gd_background_data.lon_interval)

        lon_arr = gd_background_data._lon  # already numpy float64 array
        lat_arr = gd_background_data._lat  # already numpy float64 array
        bg_val = gd_background_data.val
        xn = gd_background_data.xn
        yn = gd_background_data.yn

        # Pre-compute station arrays once
        sta_lons = np.array([pd.lon for pd in sd_input_data.sta_data], dtype=np.float64)
        sta_lats = np.array([pd.lat for pd in sd_input_data.sta_data], dtype=np.float64)
        sta_vals = np.array([pd.val for pd in sd_input_data.sta_data], dtype=np.float64)
        x_idxs = ((sta_lons + 1e-05 - gd_background_data.lon_start) /
                  gd_background_data.lon_interval).astype(np.intp)
        y_idxs = ((sta_lats + 1e-05 - gd_background_data.lat_start) /
                  gd_background_data.lat_interval).astype(np.intp)

        # Step 1: interpolate background to each station
        bg_at_sta = np.empty(length, dtype=np.float64)
        for n in range(length):
            x_start = max(0, x_idxs[n] - influence_grid)
            x_end = min(xn - 1, x_idxs[n] + influence_grid)
            y_start = max(0, y_idxs[n] - influence_grid)
            y_end = min(yn - 1, y_idxs[n] + influence_grid)

            dx = lon_arr[x_start:x_end + 1] - sta_lons[n]
            dy = lat_arr[y_start:y_end + 1] - sta_lats[n]
            dist = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
            mask = dist <= distance_limit
            if mask.any():
                weight = 1.0 / np.power(dist[mask] + smooth, power_param)
                wsum = np.sum(weight * bg_val[y_start:y_end + 1, x_start:x_end + 1][mask])
                wnorm = np.sum(weight)
                bg_at_sta[n] = float(wsum / wnorm) if wnorm >= 1e-05 else sta_vals[n]
            else:
                bg_at_sta[n] = sta_vals[n]

        increments = sta_vals - bg_at_sta

        # Step 2: distribute station increments back to grid
        grid_data = gd_background_data.copy_grid_data()
        grid_data2 = gd_background_data.copy_grid_data()
        grid_data3 = gd_background_data.copy_grid_data()
        grid_data.clear_to_num(0.0)
        grid_data2.clear_to_num(0.0)
        grid_data3.clear_to_num(0.0)

        for n in range(length):
            dval = increments[n]
            x_start = max(0, x_idxs[n] - influence_grid)
            x_end = min(xn - 1, x_idxs[n] + influence_grid)
            y_start = max(0, y_idxs[n] - influence_grid)
            y_end = min(yn - 1, y_idxs[n] + influence_grid)

            dx = lon_arr[x_start:x_end + 1] - sta_lons[n]
            dy = lat_arr[y_start:y_end + 1] - sta_lats[n]
            dist = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
            mask = dist <= distance_limit
            if mask.any():
                weight = 1.0 / np.power(dist[mask] + smooth, power_param)
                grid_data.val[y_start:y_end + 1, x_start:x_end + 1][mask] += weight * dval
                grid_data2.val[y_start:y_end + 1, x_start:x_end + 1][mask] += weight
                grid_data3.val[y_start:y_end + 1, x_start:x_end + 1][mask] += 1.0

        # Step 3: apply corrections
        mask_ok = (grid_data2.val >= 1e-05) & (grid_data3.val >= number_limit)
        grid_data.val[mask_ok] = (grid_data.val[mask_ok] / grid_data2.val[mask_ok] +
                                  gd_background_data.val[mask_ok])
        grid_data.val[~mask_ok] = gd_background_data.val[~mask_ok]
        grid_data.val[(mask_ok) & (grid_data.val <= rain_limit)] = (
            gd_background_data.val[(mask_ok) & (grid_data.val <= rain_limit)])

        return grid_data

    @staticmethod
    def gress_man_interpolation_for_rain(sd_input_data, gd_background_data, distance_limits,
                                          num_limit=1.0, smooth=0.001, power_param=2.0, rain_limit=0.01):
        """按 ``distance_limits`` 由大到小多次 Cressman，每步以上一步场为背景。"""
        grid_data = gd_background_data.copy_grid_data()
        for dlimit in distance_limits:
            grid_data = SpatialAnalisis._cressman_one_step_interpolation_for_rain(
                sd_input_data, grid_data, dlimit, num_limit, smooth, power_param, rain_limit)
        return grid_data

    @staticmethod
    def _cressman_one_step_interpolation(sd_input_data, gd_background_data, distance_limit,
                                          number_limit=1.0, smooth=0.001, power_param=2.0):
        length = len(sd_input_data.sta_data)
        influence_grid = int(distance_limit / gd_background_data.lon_interval)

        lon_arr = gd_background_data._lon  # already numpy float64
        lat_arr = gd_background_data._lat
        bg_val = gd_background_data.val
        xn = gd_background_data.xn
        yn = gd_background_data.yn

        # Pre-compute station arrays
        sta_lons = np.array([pd.lon for pd in sd_input_data.sta_data], dtype=np.float64)
        sta_lats = np.array([pd.lat for pd in sd_input_data.sta_data], dtype=np.float64)
        sta_vals = np.array([pd.val for pd in sd_input_data.sta_data], dtype=np.float64)
        x_idxs = ((sta_lons - gd_background_data.lon_start) /
                  gd_background_data.lon_interval).astype(np.intp)
        y_idxs = ((sta_lats - gd_background_data.lat_start) /
                  gd_background_data.lat_interval).astype(np.intp)

        # Step 1: background at stations
        bg_at_sta = np.empty(length, dtype=np.float64)
        for n in range(length):
            x_start = max(0, x_idxs[n] - influence_grid)
            x_end = min(xn - 1, x_idxs[n] + influence_grid)
            y_start = max(0, y_idxs[n] - influence_grid)
            y_end = min(yn - 1, y_idxs[n] + influence_grid)

            dx = lon_arr[x_start:x_end + 1] - sta_lons[n]
            dy = lat_arr[y_start:y_end + 1] - sta_lats[n]
            dist = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
            mask = dist <= distance_limit
            if mask.any():
                weight = 1.0 / np.power(dist[mask] + smooth, power_param)
                wsum = np.sum(weight * bg_val[y_start:y_end + 1, x_start:x_end + 1][mask])
                wnorm = np.sum(weight)
                bg_at_sta[n] = float(wsum / wnorm) if wnorm >= 1e-05 else sta_vals[n]
            else:
                bg_at_sta[n] = sta_vals[n]

        increments = sta_vals - bg_at_sta

        # Step 2: distribute increments back to grid
        grid_data = gd_background_data.copy_grid_data()
        grid_data2 = gd_background_data.copy_grid_data()
        grid_data3 = gd_background_data.copy_grid_data()
        grid_data.clear_to_num(0.0)
        grid_data2.clear_to_num(0.0)
        grid_data3.clear_to_num(0.0)

        for n in range(length):
            dval = increments[n]
            x_start = max(0, x_idxs[n] - influence_grid)
            x_end = min(xn - 1, x_idxs[n] + influence_grid)
            y_start = max(0, y_idxs[n] - influence_grid)
            y_end = min(yn - 1, y_idxs[n] + influence_grid)

            dx = lon_arr[x_start:x_end + 1] - sta_lons[n]
            dy = lat_arr[y_start:y_end + 1] - sta_lats[n]
            dist = np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2)
            mask = dist <= distance_limit
            if mask.any():
                weight = 1.0 / np.power(dist[mask] + smooth, power_param)
                grid_data.val[y_start:y_end + 1, x_start:x_end + 1][mask] += weight * dval
                grid_data2.val[y_start:y_end + 1, x_start:x_end + 1][mask] += weight
                grid_data3.val[y_start:y_end + 1, x_start:x_end + 1][mask] += 1.0

        mask_ok = (grid_data2.val >= 1e-05) & (grid_data3.val >= number_limit)
        grid_data.val[mask_ok] = (grid_data.val[mask_ok] / grid_data2.val[mask_ok] +
                                  gd_background_data.val[mask_ok])
        grid_data.val[~mask_ok] = gd_background_data.val[~mask_ok]

        return grid_data

    @staticmethod
    def gress_man_interpolation(sd_input_data, gd_background_data, distance_limits,
                                 num_limit=1.0, smooth=0.001, power_param=2.0):
        grid_data = gd_background_data.copy_grid_data()
        for dlimit in distance_limits:
            grid_data = SpatialAnalisis._cressman_one_step_interpolation(
                sd_input_data, grid_data, dlimit, num_limit, smooth, power_param)
        return grid_data
