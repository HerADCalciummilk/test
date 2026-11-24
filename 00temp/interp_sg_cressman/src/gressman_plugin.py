# -*- coding: utf-8 -*-
"""新增算法：rain24 原版度制幂次 Cressman（GressMan）与插值辅助。

与既有 ``interp_sg_cressman``（km / (R²−d²)/(R²+d²)）并列独立，不改动旧核。
保留 innovation 累加语义；半径单位为度。
"""
from __future__ import annotations

import pandas as pd
import meteva.base as meb
import numpy as np
import xarray as xr


def clear_to_num_greater_than(scatter_df: pd.DataFrame, number, number_limit):
    sta = scatter_df.copy()
    sta["data0"] = scatter_df["data0"].apply(lambda x: number if x >= number_limit else x)
    return sta


def sub_sta(scatter_df1: pd.DataFrame, scatter_df2: pd.DataFrame):
    scatter_df = scatter_df1.copy()
    scatter_df["data0"] = scatter_df1["data0"] - scatter_df2["data0"]
    return scatter_df


def GressManInterpolation(
    sta,
    grd,
    distance_limits,
    num_limit=1.0,
    smooth=0.001,
    power_param=2.0,
    rain_limit=None,
):
    temp_grd = grd.copy()
    for n in range(len(distance_limits)):
        temp_grd = cressman_one_step(
            sta,
            temp_grd,
            distance_limits[n],
            rain_limit,
            num_limit,
            smooth,
            power_param,
        )
    return temp_grd


def cressman_one_step(
    sd_input_data,
    gd_background_data,
    distance_limit,
    rain_limit,
    number_limit=1.0,
    smooth=0.001,
    power_param=2.0,
):
    grid_info = meb.basicdata.get_grid_of_data(gd_background_data)
    delt_lon, delt_lat, lon_count, lat_count = (
        grid_info.dlon,
        grid_info.dlat,
        grid_info.nlon,
        grid_info.nlat,
    )
    start_lon, start_lat = grid_info.slon, grid_info.slat

    sta_num = len(sd_input_data)
    sd_from_background = sd_input_data.copy()
    scatter_data = sd_input_data.copy()
    influence_grid = int(distance_limit / delt_lon)
    sd_from_background = clear_to_num_greater_than(sd_from_background, 0, 0)

    lon_grd = gd_background_data.lon.to_numpy()
    lat_grd = gd_background_data.lat.to_numpy()
    data_array = gd_background_data.data.squeeze()

    sta_lon, sta_lat, sta_data = (
        sd_input_data["lon"].to_numpy(),
        sd_input_data["lat"].to_numpy(),
        sd_input_data["data0"].to_numpy(),
    )
    sd_from_background["data0"] = update_sta(
        sta_num,
        sta_lon,
        sta_lat,
        sta_data,
        start_lon,
        start_lat,
        lon_count,
        lat_count,
        delt_lon,
        influence_grid,
        lon_grd,
        lat_grd,
        distance_limit,
        smooth,
        power_param,
        data_array,
    )

    scatter_data = sub_sta(scatter_data, sd_from_background)
    grid_data = meb.grid_data(grid_info)
    grid_array1 = grid_data.copy().data.squeeze()
    grid_array2 = grid_array1.copy()
    grid_array3 = grid_array1.copy()

    sta_lon, sta_lat, sta_data = (
        scatter_data["lon"].to_numpy(),
        scatter_data["lat"].to_numpy(),
        scatter_data["data0"].to_numpy(),
    )
    grid_array1, grid_array2, grid_array3 = update_array(
        sta_num,
        sta_lon,
        sta_lat,
        sta_data,
        start_lon,
        start_lat,
        lon_count,
        lat_count,
        delt_lon,
        influence_grid,
        lon_grd,
        lat_grd,
        distance_limit,
        smooth,
        power_param,
        grid_array1,
        grid_array2,
        grid_array3,
    )
    grid_array4 = grid_array1 / grid_array2 + data_array
    if rain_limit is not None:
        grid_array4 = np.where(grid_array4 <= rain_limit, data_array, grid_array4)
    opt_array = np.where(
        (grid_array2 >= 1e-5) & (grid_array3 >= number_limit),
        grid_array4,
        data_array,
    )
    grid_data.data = [[[[opt_array]]]]
    return grid_data


def update_sta(
    sta_num,
    sta_lon,
    sta_lat,
    sta_data,
    start_lon,
    start_lat,
    lon_count,
    lat_count,
    delt_lon,
    influence_grid,
    lon_grd,
    lat_grd,
    distance_limit,
    smooth,
    power_param,
    data_array,
):
    sta_data_update = []
    distance_limit_sq = distance_limit**2
    for n in range(sta_num):
        num1 = int((sta_lon[n] + 1e-5 - start_lon) / delt_lon)
        num2 = int((sta_lat[n] + 1e-5 - start_lat) / delt_lon)

        num3 = max(num1 - influence_grid, 0)
        num4 = min(num1 + influence_grid, lon_count - 1)
        num5 = max(num2 - influence_grid, 0)
        num6 = min(num2 + influence_grid, lat_count - 1)

        influence_lon = lon_grd[num3 : num4 + 1]
        influence_lat = lat_grd[num5 : num6 + 1]
        influence_data = data_array[num5 : num6 + 1, num3 : num4 + 1]

        delta_lon = influence_lon - sta_lon[n]
        delta_lat = influence_lat[:, np.newaxis] - sta_lat[n]
        distance_sq = delta_lon**2 + delta_lat**2

        mask = distance_sq <= distance_limit_sq
        distance = np.sqrt(distance_sq[mask])
        weights = 1.0 / ((distance + smooth) ** power_param)

        weighted_sum = np.sum(weights * influence_data[mask])
        weight_sum = np.sum(weights)

        if weight_sum >= 1e-5:
            data0 = weighted_sum / weight_sum
        else:
            data0 = sta_data[n]

        sta_data_update.append(data0)
    return sta_data_update


def update_array(
    sta_num,
    sta_lon,
    sta_lat,
    sta_data,
    start_lon,
    start_lat,
    lon_count,
    lat_count,
    delt_lon,
    influence_grid,
    lon_grd,
    lat_grd,
    distance_limit,
    smooth,
    power_param,
    grid_array1,
    grid_array2,
    grid_array3,
):
    distance_limit_sq = distance_limit**2
    for sta_idx in range(sta_num):
        grid_x = int((sta_lon[sta_idx] - start_lon) / delt_lon)
        grid_y = int((sta_lat[sta_idx] - start_lat) / delt_lon)

        x_min = max(grid_x - influence_grid, 0)
        x_max = min(grid_x + influence_grid, lon_count - 1)
        y_min = max(grid_y - influence_grid, 0)
        y_max = min(grid_y + influence_grid, lat_count - 1)

        influence_lon = lon_grd[x_min : x_max + 1]
        influence_lat = lat_grd[y_min : y_max + 1]

        delta_lon = influence_lon - sta_lon[sta_idx]
        delta_lat = influence_lat[:, np.newaxis] - sta_lat[sta_idx]
        distance_sq = delta_lon**2 + delta_lat**2

        mask = distance_sq <= distance_limit_sq
        distance = np.sqrt(distance_sq[mask])

        weights = 1.0 / ((distance + smooth) ** power_param)

        grid_array1[y_min : y_max + 1, x_min : x_max + 1][mask] += weights * sta_data[sta_idx]
        grid_array2[y_min : y_max + 1, x_min : x_max + 1][mask] += weights
        grid_array3[y_min : y_max + 1, x_min : x_max + 1][mask] += 1.0

    return grid_array1, grid_array2, grid_array3


def mesh_val(grd, inter_extend):
    grid_info = meb.basicdata.get_grid_of_data(grd)
    grd_lon, grd_lat, grd_array = grd.lon.to_numpy(), grd.lat.to_numpy(), grd.data.squeeze().copy()

    slon, elon, slat, elat, res = inter_extend
    inter_lon = np.round(np.arange(slon, elon + 1e-5, res), 4)
    inter_lat = np.round(np.arange(slat, elat + 1e-5, res), 4)
    if len(inter_lon) == 1:
        inter_lon = np.append(inter_lon, inter_lon[0] + res)
    if len(inter_lat) == 1:
        inter_lat = np.append(inter_lat, inter_lat[0] + res)
    grd_array_inter = bilinear_interp_grd(
        grd_array,
        len(inter_lon),
        len(inter_lat),
        grd_lon,
        grd_lat,
        grid_info.slon,
        grid_info.slat,
        grid_info.dlon,
        grid_info.dlat,
        grid_info.nlon,
        grid_info.nlat,
        inter_lon,
        inter_lat,
    )
    da0 = xr.DataArray(grd_array_inter, coords=[inter_lat, inter_lon], dims=["lat", "lon"])
    grd_inter = meb.xarray_to_griddata(da0)
    grd_inter["member"] = grd.member
    return grd_inter


def bilinear_interp(grd, sta, dbUndef=0.0):
    length = len(sta)
    grd_array = grd.data.squeeze().copy()
    grd_lon, grd_lat = grd.lon.to_numpy(), grd.lat.to_numpy()
    sta_lon, sta_lat = sta.lon.to_numpy(), sta.lat.to_numpy()
    grid_info = meb.basicdata.get_grid_of_data(grd)
    data_list = bilinear_interp_sta(
        length,
        sta_lon,
        sta_lat,
        grid_info.slon,
        grid_info.slat,
        grid_info.dlon,
        grid_info.dlat,
        grid_info.nlon,
        grid_info.nlat,
        grd_array,
        grd_lon,
        grd_lat,
        dbUndef,
    )
    inter_sta = sta.copy()
    inter_sta.data0 = data_list
    return inter_sta


def bilinear_interp_grd(
    grd_array,
    local_xn,
    local_yn,
    grd_lon,
    grd_lat,
    start_lon,
    start_lat,
    delt_lon,
    delt_lat,
    lon_count,
    lat_count,
    inter_lon,
    inter_lat,
):
    grd_array_inter = np.zeros((local_yn, local_xn))
    inter_lon_grd, inter_lat_grd = np.meshgrid(inter_lon, inter_lat)

    index3 = np.floor((inter_lon_grd - start_lon + 1e-5) / delt_lon).astype(int)
    index4 = np.floor((inter_lat_grd - start_lat + 1e-5) / delt_lat).astype(int)

    mask = (index3 >= 0) & (index3 <= lon_count - 2) & (index4 >= 0) & (index4 <= lat_count - 2)
    mask_edge1 = (index3 == lon_count - 1) & (index4 <= lat_count - 2) & (index4 >= 0)
    mask_edge2 = (index3 >= 0) & (index3 <= lon_count - 2) & (index4 == lat_count - 1)
    mask_edge3 = (index3 == lon_count - 1) & (index4 == lat_count - 1)

    num1 = (
        grd_array[index4[mask], index3[mask]] * (grd_lon[index3[mask] + 1] - inter_lon_grd[mask])
        + grd_array[index4[mask], index3[mask] + 1] * (inter_lon_grd[mask] - grd_lon[index3[mask]])
    ) / delt_lon
    num2 = (
        grd_array[index4[mask] + 1, index3[mask]] * (grd_lon[index3[mask] + 1] - inter_lon_grd[mask])
        + grd_array[index4[mask] + 1, index3[mask] + 1]
        * (inter_lon_grd[mask] - grd_lon[index3[mask]])
    ) / delt_lon
    num3 = grd_lat[index4[mask] + 1] - inter_lat_grd[mask]
    grd_array_inter[mask] = (num1 * num3 + num2 * (inter_lat_grd[mask] - grd_lat[index4[mask]])) / delt_lat

    grd_array_inter[mask_edge1] = (
        grd_array[index4[mask_edge1], index3[mask_edge1]]
        * (grd_lat[index4[mask_edge1] + 1] - inter_lat_grd[mask_edge1])
        + grd_array[index4[mask_edge1] + 1, index3[mask_edge1]]
        * (inter_lat_grd[mask_edge1] - grd_lat[index4[mask_edge1]])
    ) / delt_lat

    grd_array_inter[mask_edge2] = (
        grd_array[index4[mask_edge2], index3[mask_edge2]]
        * (grd_lon[index3[mask_edge2] + 1] - inter_lon_grd[mask_edge2])
        + grd_array[index4[mask_edge2], index3[mask_edge2] + 1]
        * (inter_lon_grd[mask_edge2] - grd_lon[index3[mask_edge2]])
    ) / delt_lon

    grd_array_inter[mask_edge3] = grd_array[index4[mask_edge3], index3[mask_edge3]]

    return grd_array_inter


def bilinear_interp_sta(
    length,
    sta_lon,
    sta_lat,
    start_lon,
    start_lat,
    delt_lon,
    delt_lat,
    lon_count,
    lat_count,
    grd_array,
    grd_lon,
    grd_lat,
    db_undef,
):
    index2 = ((sta_lon + 1e-5 - start_lon) / delt_lon).astype(int)
    index3 = ((sta_lat + 1e-5 - start_lat) / delt_lat).astype(int)

    mask = (index2 >= 0) & (index2 < lon_count - 1) & (index3 >= 0) & (index3 < lat_count - 1)

    data_list = np.full(length, db_undef)

    valid_index2 = index2[mask]
    valid_index3 = index3[mask]

    num1 = (
        grd_array[valid_index3, valid_index2] * (grd_lon[valid_index2 + 1] - sta_lon[mask])
        + grd_array[valid_index3, valid_index2 + 1] * (sta_lon[mask] - grd_lon[valid_index2])
    ) / delt_lon
    num2 = (
        grd_array[valid_index3 + 1, valid_index2] * (grd_lon[valid_index2 + 1] - sta_lon[mask])
        + grd_array[valid_index3 + 1, valid_index2 + 1] * (sta_lon[mask] - grd_lon[valid_index2])
    ) / delt_lon
    num3 = grd_lat[valid_index3 + 1] - sta_lat[mask]

    data_list[mask] = (num1 * num3 + num2 * (sta_lat[mask] - grd_lat[valid_index3])) / delt_lat

    return data_list


class GressMan:
    """插件入口，签名对齐 ``GressManInterpolation``。"""

    def process(self, sta, grd, distance_limits, **kw):
        return GressManInterpolation(sta, grd, distance_limits, **kw)


__all__ = [
    "GressMan",
    "GressManInterpolation",
    "bilinear_interp",
    "bilinear_interp_grd",
    "bilinear_interp_sta",
    "cressman_one_step",
    "mesh_val",
    "update_array",
    "update_sta",
]
