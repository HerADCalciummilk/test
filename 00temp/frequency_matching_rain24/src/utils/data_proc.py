# -- coding: utf-8 --
# @Time : 2025/1/20 9:28
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : dataProc.py
# @Software: PyCharm
import meteva
import pandas as pd
import xarray as xr
import numpy as np
import meteva.base as meb
from datetime import datetime
from scipy.ndimage import convolve

def creat_M3_grd(Lon_list, Lat_list, Data_list, rpt=None, dtime=0):
    data = {
        "Lon": Lon_list,
        "Lat": Lat_list,
        "Data": Data_list,
    }
    # 构建站点数据标准格式
    M3_grd = pd.DataFrame(data)
    sta = meb.sta_data(M3_grd, columns=["lon", "lat", 'data0'])
    meb.set_stadata_coords(sta, level=0, time=rpt, dtime=dtime)
    return sta

def GetNumUp(left, right):
    if left >= right:
        return []

    remainder = left % 5
    next_left_num = left if remainder == 0 else left + (5 - remainder)

    left_list = []
    left_list.append(left)

    while next_left_num < right:
        if next_left_num > left:
            left_list.append(next_left_num)
        next_left_num += 5.0
    return left_list

def GetNumDown(left, right):
    if left >= right:
        return []

    remainder = left % 5
    next_right_num = left if remainder == 0 else left + (5 - remainder)

    right_list = []
    while next_right_num < right:
        if next_right_num > left:
            right_list.append(next_right_num)
        next_right_num += 5.0

    right_list.append(right)
    return right_list

def clear_to_num_greater_than(scatter_df: pd.DataFrame, number, number_limit):
    sta = scatter_df.copy()
    sta['data0'] = scatter_df['data0'].apply(lambda x: number if x >= number_limit else x)
    return sta

def clear_to_num_less_than(scatter_df: pd.DataFrame, number, number_limit):
    sta = scatter_df.copy()
    sta['data0'] = scatter_df['data0'].apply(lambda x: number if x < number_limit else x)
    return sta

def clear_to_num_less_than_grd(grd: xr.DataArray, number, number_limit):
    grd_meb = grd.copy()
    grd_array = grd_meb.data.squeeze()
    grd_array[grd_array < number_limit] = number
    grd_array[grd_array > 9999.] = 9999.
    grd_meb.data = [[[[grd_array]]]]
    return grd_meb

def sub_sta(scatter_df1: pd.DataFrame, scatter_df2: pd.DataFrame):
    scatter_df = scatter_df1.copy()
    scatter_df['data0'] = scatter_df1['data0'] - scatter_df2['data0']
    return scatter_df

def select_by_extend(scatter_df: pd.DataFrame, extend):
    sta = scatter_df[(scatter_df['lon'] >= extend[0])
                     & (scatter_df['lon'] < extend[1])
                     & (scatter_df['lat'] >= extend[2])
                     & (scatter_df['lat'] < extend[3])
                     ]
    return sta

def grid_data_fix_by_scatter(scatter_df: pd.DataFrame, grd: xr.DataArray):
    grd_meb = grd.copy()
    grd_array, flag_array = grd_meb.data.squeeze(), grd_meb.data.squeeze() * 0.0
    grid_info = meb.basicdata.get_grid_of_data(grd)
    delt_lon, delt_lat, lon_count, lat_count = grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat
    start_lon, end_lon, start_lat, end_lat = grid_info.slon, grid_info.elon, grid_info.slat, grid_info.elat

    # 计算每个站点的网格索引
    lon_indices = np.round((scatter_df['lon'].values - start_lon) / delt_lon).astype(int)
    lat_indices = np.round((scatter_df['lat'].values - start_lat) / delt_lat).astype(int)

    # 过滤掉超出网格范围的索引
    valid_mask = (lon_indices >= 0) & (lon_indices < grid_info.nlon) & \
                 (lat_indices >= 0) & (lat_indices < grid_info.nlat)
    lon_indices = lon_indices[valid_mask]
    lat_indices = lat_indices[valid_mask]
    data_values = scatter_df['data0'].values[valid_mask]

    # 使用 numpy 的高级索引更新 grd_array 和 flag_array
    for lon_idx, lat_idx, data_value in zip(lon_indices, lat_indices, data_values):
        if flag_array[lat_idx, lon_idx] == 0.0:
            grd_array[lat_idx, lon_idx] = data_value
            flag_array[lat_idx, lon_idx] = 1.0
        else:
            grd_array[lat_idx, lon_idx] = max(grd_array[lat_idx, lon_idx], data_value)

    # for n in range(len(scatter_df)):
    #     index1 = int(round((scatter_df.iloc[n].lon - start_lon) / delt_lon))
    #     index2 = int(round((scatter_df.iloc[n].lat - start_lat) / delt_lat))
    #     if (index1 < 0) or (index1 >= lon_count) or (index2 < 0) or (index2 >= lat_count):
    #         continue
    #     if flag_array[index2][index1] == 0.0:
    #         grd_array[index2][index1] = scatter_df.iloc[n].data0
    #         flag_array[index2][index1] = 1.0
    #     else:
    #         if scatter_df.iloc[n].data0 < grd_array[index2][index1]:
    #             continue
    #         grd_array[index2][index1] = scatter_df.iloc[n].data0

    grd_meb.data = [[[[grd_array]]]]
    return grd_meb

def subtilize_grd(grd: xr.DataArray, mask: np.array, inter):
    lon, lat = grd.lon.to_numpy(), grd.lat.to_numpy()
    lon_mesh, lat_mesh = np.meshgrid(lon, lat)
    current_model_data = grd.data.squeeze()
    mask_data = mask[::inter, ::inter].flatten()
    lon_new, lat_new = lon_mesh[::inter, ::inter].flatten(), lat_mesh[::inter, ::inter].flatten()
    data_new = current_model_data[::inter, ::inter].flatten()
    lon_new = lon_new[mask_data < 0]
    lat_new = lat_new[mask_data < 0]
    data_new = data_new[mask_data < 0]
    return lon_new, lat_new, data_new

def mask_grd(grd: xr.DataArray, mask: xr.DataArray):
    grd_meb = grd.copy()
    grd_array = grd.data.squeeze()
    mask_array = mask.data.squeeze()
    array = np.where(mask_array <= 0,  0, grd_array)
    grd_meb.data = [[[[array]]]]
    return grd_meb

def smooth9(grd: xr.DataArray, smooth_times = 1):
    if (grd is None):
        return None
    grd_meb = grd.copy()
    val, num_array = grd_meb.data.squeeze(), grd_meb.data.squeeze() * 0
    xn, yn = len(grd_meb.lon), len(grd_meb.lat)
    kernel = np.array([[0.0625, 0.125, 0.0625],
                       [0.125, 0.25, 0.125],
                       [0.0625, 0.125, 0.0625]])

    for _ in range(smooth_times):
        # num_array[1:yn - 1, 1:xn - 1] = 0.25 * (0.25 * val[2:yn, 0:xn - 2] +
        #                                         0.5 * val[2:yn, 1:xn - 1] +
        #                                         0.25 * val[2:yn, 2:xn]) + \
        #                                 0.5 * (0.25 * val[1:yn - 1, 0:xn - 2] +
        #                                        0.5 * val[1:yn - 1, 1:xn - 1] +
        #                                        0.25 * val[1:yn - 1, 2:xn]) + \
        #                                 0.25 * (0.25 * val[0:yn - 2, 0:xn - 2] +
        #                                         0.5 * val[0:yn - 2, 1:xn - 1] +
        #                                         0.25 * val[0:yn - 2, 2:xn])
        num_array[1:yn - 1, 1:xn - 1] = convolve(val, kernel)[1:yn - 1, 1:xn - 1]
        num_array[1:yn - 1, 0] = num_array[1:yn - 1, 1] + (num_array[1:yn - 1, 1] - num_array[1:yn - 1, 2])
        num_array[1:yn - 1, xn - 1] = num_array[1:yn - 1, xn - 2] + (
                    num_array[1:yn - 1, xn - 2] - num_array[1:yn - 1, xn - 3])

        num_array[0, :] = num_array[1, :] + (num_array[1, :] - num_array[2, :])
        num_array[yn - 1, :] = num_array[yn - 2, :] + (num_array[yn - 2, :] - num_array[yn - 3, :])

        val = num_array.copy()
        val[val <= 0.0] = 0.0

    grd_meb.data = [[[[val]]]]
    return grd_meb

def StandardizeByMaxMin(grd: xr.DataArray, minVal, maxVal):
    grd_meb = grd.copy()
    grd_array = grd_meb.data.squeeze()
    val = np.where(grd_array < minVal, 0.0,
                   np.where(grd_array >= maxVal, 1.0,  (grd_array - minVal) / (maxVal - minVal)))
    grd_meb.data = [[[[val]]]]
    return grd_meb

def MultiValFormNewGridData(grd_flow: xr.DataArray, grd: xr.DataArray):
    grd_meb = grd.copy()
    grd_array = grd_meb.data.squeeze()
    return grd_flow * grd_array