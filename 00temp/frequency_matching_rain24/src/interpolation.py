# -- coding: utf-8 --
# @Time : 2025/2/14 9:38
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : interpolation.py
# @Software: PyCharm
import math
from utils.data_proc import *
# from numba import njit, prange

def GressManInterpolation(sta, grd, distance_limits, num_limit=1.0, smooth=0.001, power_param=2.0, rain_limit=None):
    temp_grd = grd.copy()
    for n in range(len(distance_limits)):
        temp_grd = cressman_one_step(sta, temp_grd, distance_limits[n], rain_limit, num_limit, smooth, power_param)
    return temp_grd

def cressman_one_step(sd_input_data, gd_background_data, distance_limit, rain_limit, number_limit=1.0, smooth=0.001,
        power_param=2.0):

    grid_info = meb.basicdata.get_grid_of_data(gd_background_data)
    delt_lon, delt_lat, lon_count, lat_count = grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat
    start_lon, start_lat = grid_info.slon, grid_info.slat

    sta_num = len(sd_input_data)
    sdFromBackground = sd_input_data.copy()
    scatterData = sd_input_data.copy()
    InfluenceGrid = int(distance_limit / delt_lon)
    sdFromBackground = clear_to_num_greater_than(sdFromBackground, 0, 0)

    lon_grd = gd_background_data.lon.to_numpy()
    lat_grd = gd_background_data.lat.to_numpy()
    data_array = gd_background_data.data.squeeze()

    sta_lon, sta_lat, sta_data = sd_input_data['lon'].to_numpy(), sd_input_data['lat'].to_numpy(), sd_input_data['data0'].to_numpy()
    sdFromBackground['data0'] = update_sta(sta_num, sta_lon, sta_lat, sta_data, start_lon, start_lat, lon_count, lat_count,
                         delt_lon, InfluenceGrid, lon_grd, lat_grd, distance_limit, smooth, power_param, data_array)

    scatterData = sub_sta(scatterData, sdFromBackground)
    gridData = meb.grid_data(grid_info)
    grid_array1 = gridData.copy().data.squeeze()
    grid_array2 = grid_array1.copy()
    grid_array3 = grid_array1.copy()

    sta_lon, sta_lat, sta_data = scatterData['lon'].to_numpy(), scatterData['lat'].to_numpy(), scatterData['data0'].to_numpy()
    grid_array1, grid_array2, grid_array3 = update_array(sta_num, sta_lon, sta_lat, sta_data, start_lon, start_lat, lon_count,
                       lat_count, delt_lon, InfluenceGrid, lon_grd, lat_grd, distance_limit, smooth, power_param, grid_array1,
                       grid_array2, grid_array3)
    grid_array4 = grid_array1 / grid_array2 + data_array
    if rain_limit is not None:
        grid_array4 = np.where(grid_array4 <= rain_limit, data_array, grid_array4)
    opt_array = np.where((grid_array2 >= 1E-05) & (grid_array3 >= number_limit), grid_array4, data_array)
    gridData.data = [[[[opt_array]]]]
    return gridData

def update_sta(sta_num, sta_lon, sta_lat, sta_data, start_lon, start_lat, lon_count, lat_count, delt_lon, InfluenceGrid, lon_grd,
               lat_grd, distance_limit, smooth, power_param, data_array):
    sta_data_update = []
    distance_limit_sq = distance_limit ** 2
    for n in range(sta_num):
        num1 = int((sta_lon[n] + 1E-05 - start_lon) / delt_lon)
        num2 = int((sta_lat[n] + 1E-05 - start_lat) / delt_lon)

        num3 = max(num1 - InfluenceGrid, 0)
        num4 = min(num1 + InfluenceGrid, lon_count - 1)
        num5 = max(num2 - InfluenceGrid, 0)
        num6 = min(num2 + InfluenceGrid, lat_count - 1)

        influence_lon = lon_grd[num3:num4 + 1]
        influence_lat = lat_grd[num5:num6 + 1]
        influence_data = data_array[num5:num6 + 1, num3:num4 + 1]

        delta_lon = influence_lon - sta_lon[n]
        delta_lat = influence_lat[:, np.newaxis] - sta_lat[n]
        distance_sq = delta_lon ** 2 + delta_lat ** 2

        mask = distance_sq <= distance_limit_sq
        distance = np.sqrt(distance_sq[mask])
        weights = 1.0 / ((distance + smooth) ** power_param)

        weighted_sum = np.sum(weights * influence_data[mask])
        weight_sum = np.sum(weights)

        if weight_sum >= 1E-05:
            data0 = weighted_sum / weight_sum
        else:
            data0 = sta_data[n]

        sta_data_update.append(data0)
    return sta_data_update

def update_array(sta_num, sta_lon, sta_lat, sta_data, start_lon, start_lat, lon_count, lat_count, delt_lon, InfluenceGrid, lon_grd,
                 lat_grd, distance_limit, smooth, power_param, grid_array1, grid_array2, grid_array3):
    # for index3 in range(sta_num):
    #     num13 = int((sta_lon[index3] - start_lon) / delt_lon)
    #     num14 = int((sta_lat[index3] - start_lat) / delt_lon)
    #     num15 = num13 - InfluenceGrid
    #     if num15 < 0:
    #         num15 = 0
    #     num16 = num13 + InfluenceGrid
    #     if num16 > lon_count - 1:
    #         num16 = lon_count - 1
    #     num17 = num14 - InfluenceGrid
    #     if num17 < 0:
    #         num17 = 0
    #     num18 = num14 + InfluenceGrid
    #     if num18 > lat_count - 1:
    #         num18 = lat_count - 1
    #     for index4 in range(num17, num18 + 1):
    #         for index5 in range(num15, num16 + 1):
    #             num19 = lon_grd[index5] - sta_lon[index3]
    #             num20 = lat_grd[index4] - sta_lat[index3]
    #             num21 = np.sqrt(num19 * num19 + num20 * num20)
    #             if num21 <= distance_limit:
    #                 num22 = 1.0 / np.power(num21 + smooth, power_param)
    #                 grid_array1[index4][index5] = grid_array1[index4][index5] + num22 * sta_data[index3]
    #                 grid_array2[index4][index5] = grid_array2[index4][index5] + num22
    #                 grid_array3[index4][index5] = grid_array3[index4][index5] + 1.0

    distance_limit_sq = distance_limit ** 2
    for sta_idx in range(sta_num):
        grid_x = int((sta_lon[sta_idx] - start_lon) / delt_lon)
        grid_y = int((sta_lat[sta_idx] - start_lat) / delt_lon)

        x_min = max(grid_x - InfluenceGrid, 0)
        x_max = min(grid_x + InfluenceGrid, lon_count - 1)
        y_min = max(grid_y - InfluenceGrid, 0)
        y_max = min(grid_y + InfluenceGrid, lat_count - 1)

        influence_lon = lon_grd[x_min:x_max + 1]
        influence_lat = lat_grd[y_min:y_max + 1]

        delta_lon = influence_lon - sta_lon[sta_idx]
        delta_lat = influence_lat[:, np.newaxis] - sta_lat[sta_idx]
        distance_sq = delta_lon ** 2 + delta_lat ** 2

        mask = distance_sq <= distance_limit_sq
        distance = np.sqrt(distance_sq[mask])

        weights = 1.0 / ((distance + smooth) ** power_param)

        grid_array1[y_min:y_max + 1, x_min:x_max + 1][mask] += weights * sta_data[sta_idx]
        grid_array2[y_min:y_max + 1, x_min:x_max + 1][mask] += weights
        grid_array3[y_min:y_max + 1, x_min:x_max + 1][mask] += 1.0

    return grid_array1, grid_array2, grid_array3

def mesh_val(grd, inter_extend):

    grid_info = meb.basicdata.get_grid_of_data(grd)
    grd_lon, grd_lat, grd_array = grd.lon.to_numpy(), grd.lat.to_numpy(), grd.data.squeeze().copy()

    slon, elon, slat, elat, res = inter_extend
    inter_lon = np.round(np.arange(slon, elon + 1E-05, res), 4)
    inter_lat = np.round(np.arange(slat, elat + 1E-05, res), 4)
    if len(inter_lon) == 1:
        inter_lon = np.append(inter_lon, inter_lon[0] + res)
    if len(inter_lat) == 1:
        inter_lat = np.append(inter_lat, inter_lat[0] + res)
    grd_array_inter = bilinear_interp_grd(grd_array, len(inter_lon), len(inter_lat), grd_lon, grd_lat, grid_info.slon,
                                          grid_info.slat, grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat,
                                          inter_lon, inter_lat)
    da0 = xr.DataArray(grd_array_inter, coords=[inter_lat, inter_lon], dims=['lat', 'lon'])
    grd_inter = meb.xarray_to_griddata(da0)
    grd_inter['member'] = grd.member
    return grd_inter

def bilinear_interp(grd, sta, dbUndef=0.0):
    length = len(sta)
    grd_array = grd.data.squeeze().copy()
    grd_lon, grd_lat = grd.lon.to_numpy(), grd.lat.to_numpy()
    sta_lon, sta_lat = sta.lon.to_numpy(), sta.lat.to_numpy()
    grid_info = meb.basicdata.get_grid_of_data(grd)
    data_list = bilinear_interp_sta(length, sta_lon, sta_lat, grid_info.slon, grid_info.slat, grid_info.dlon,
                                    grid_info.dlat, grid_info.nlon, grid_info.nlat, grd_array, grd_lon, grd_lat, dbUndef)
    inter_sta = sta.copy()
    inter_sta.data0 = data_list
    return inter_sta

def bilinear_interp_grd(grd_array, localXn, localYn, grd_lon, grd_lat, start_lon, start_lat, delt_lon,
                                     delt_lat, lon_count, lat_count, inter_lon, inter_lat):
    grd_array_inter = np.zeros((localYn, localXn))
    inter_lon_grd, inter_lat_grd = np.meshgrid(inter_lon, inter_lat)

    index3 = np.floor((inter_lon_grd - start_lon + 1E-05) / delt_lon).astype(int)
    index4 = np.floor((inter_lat_grd - start_lat + 1E-05) / delt_lat).astype(int)

    # 创建掩码以处理边界条件
    mask = (index3 >= 0) & (index3 <= lon_count - 2) & (index4 >= 0) & (index4 <= lat_count - 2)
    mask_edge1 = (index3 == lon_count - 1) & (index4 <= lat_count - 2) & (index4 >= 0)
    mask_edge2 = (index3 >= 0) & (index3 <= lon_count - 2) & (index4 == lat_count - 1)
    mask_edge3 = (index3 == lon_count - 1) & (index4 == lat_count - 1)

    # 处理内部点
    num1 = (grd_array[index4[mask], index3[mask]] * (grd_lon[index3[mask] + 1] - inter_lon_grd[mask]) +
            grd_array[index4[mask], index3[mask] + 1] * (inter_lon_grd[mask] - grd_lon[index3[mask]])) / delt_lon
    num2 = (grd_array[index4[mask] + 1, index3[mask]] * (grd_lon[index3[mask] + 1] - inter_lon_grd[mask]) +
            grd_array[index4[mask] + 1, index3[mask] + 1] * (inter_lon_grd[mask] - grd_lon[index3[mask]])) / delt_lon
    num3 = grd_lat[index4[mask] + 1] - inter_lat_grd[mask]
    grd_array_inter[mask] = (num1 * num3 + num2 * (inter_lat_grd[mask] - grd_lat[index4[mask]])) / delt_lat

    # 处理边缘情况
    grd_array_inter[mask_edge1] = (grd_array[index4[mask_edge1], index3[mask_edge1]] * (
                grd_lat[index4[mask_edge1] + 1] - inter_lat_grd[mask_edge1]) +
                                   grd_array[index4[mask_edge1] + 1, index3[mask_edge1]] * (
                                               inter_lat_grd[mask_edge1] - grd_lat[index4[mask_edge1]])) / delt_lat

    grd_array_inter[mask_edge2] = (grd_array[index4[mask_edge2], index3[mask_edge2]] * (
                grd_lon[index3[mask_edge2] + 1] - inter_lon_grd[mask_edge2]) +
                                   grd_array[index4[mask_edge2], index3[mask_edge2] + 1] * (
                                               inter_lon_grd[mask_edge2] - grd_lon[index3[mask_edge2]])) / delt_lon

    grd_array_inter[mask_edge3] = grd_array[index4[mask_edge3], index3[mask_edge3]]

    return grd_array_inter


def bilinear_interp_sta(length, sta_lon, sta_lat, start_lon, start_lat, delt_lon, delt_lat, lon_count,
                                 lat_count, grd_array, grd_lon, grd_lat, dbUndef):
    # 计算索引
    index2 = ((sta_lon + 1E-05 - start_lon) / delt_lon).astype(int)
    index3 = ((sta_lat + 1E-05 - start_lat) / delt_lat).astype(int)

    # 创建掩码，判断索引是否在有效范围内
    mask = (index2 >= 0) & (index2 < lon_count - 1) & (index3 >= 0) & (index3 < lat_count - 1)

    # 初始化结果数组
    data_list = np.full(length, dbUndef)

    # 提取有效索引
    valid_index2 = index2[mask]
    valid_index3 = index3[mask]

    # 计算插值
    num1 = (grd_array[valid_index3, valid_index2] * (grd_lon[valid_index2 + 1] - sta_lon[mask]) +
            grd_array[valid_index3, valid_index2 + 1] * (sta_lon[mask] - grd_lon[valid_index2])) / delt_lon
    num2 = (grd_array[valid_index3 + 1, valid_index2] * (grd_lon[valid_index2 + 1] - sta_lon[mask]) +
            grd_array[valid_index3 + 1, valid_index2 + 1] * (sta_lon[mask] - grd_lon[valid_index2])) / delt_lon
    num3 = grd_lat[valid_index3 + 1] - sta_lat[mask]

    data_list[mask] = (num1 * num3 + num2 * (sta_lat[mask] - grd_lat[valid_index3])) / delt_lat

    return data_list

# @njit(parallel=True)
# def bilinear_interp_sta_parallel(length, sta_lon, sta_lat, start_lon, start_lat, delt_lon, delt_lat, lon_count, lat_count, grd_array, grd_lon,
#                grd_lat, dbUndef):
#     data_list = np.zeros_like(sta_lon)
#     for index1 in prange(length):
#         index2 = int((sta_lon[index1] + 1E-05 - start_lon) / delt_lon)
#         index3 = int((sta_lat[index1] + 1E-05 - start_lat) / delt_lat)
#         if index2 >= 0 & (index2 < lon_count - 1) & index3 >= 0 & (index3 < lat_count - 1):
#             num1 = (grd_array[index3][index2] * (grd_lon[index2 + 1] - sta_lon[index1]) +
#                     grd_array[index3][index2 + 1] * (sta_lon[index1] - grd_lon[index2])) / delt_lon
#             num2 = (grd_array[index3 + 1][index2] * (grd_lon[index2 + 1] - sta_lon[index1]) +
#                     grd_array[index3 + 1][index2 + 1] * (sta_lon[index1] - grd_lon[index2])) / delt_lon
#             num3 = grd_lat[index3 + 1] - sta_lat[index1]
#             data_list[index1] = (num1 * num3 + num2 * (sta_lat[index1] - grd_lat[index3])) / delt_lat
#         else:
#             data_list[index1] = dbUndef
#     return data_list
#
# @njit(parallel=True)
# def bilinear_interp_grd_parallel(grd_array, localXn, localYn, grd_lon, grd_lat, start_lon, start_lat, delt_lon, delt_lat,
#                  lon_count, lat_count, inter_lon, inter_lat):
#
#     grd_array_inter = np.zeros((localYn, localXn))
#     for index1 in prange(localYn):
#         for index2 in prange(localXn):
#             index3 = int(math.floor((inter_lon[index2] - start_lon + 1E-05) / delt_lon))
#             index4 = int(math.floor((inter_lat[index1] - start_lat + 1E-05) / delt_lat))
#             if (index3 >= 0) and (index3 < lon_count - 1) and (index4 >= 0) and (index4 < lat_count - 1):
#                 num1 = (grd_array[index4][index3] * (grd_lon[index3 + 1] - inter_lon[index2]) +
#                         grd_array[index4][index3 + 1] * (inter_lon[index2] - grd_lon[index3])) / delt_lon
#                 num2 = (grd_array[index4 + 1][index3] * (grd_lon[index3 + 1] - inter_lon[index2]) +
#                         grd_array[index4 + 1][index3 + 1] * (inter_lon[index2] - grd_lon[index3])) / delt_lon
#                 num3 = grd_lat[index4 + 1] - inter_lat[index1]
#                 grd_array_inter[index1][index2] = (num1 * num3 + num2 * (
#                             inter_lat[index1] - grd_lat[index4])) / delt_lat
#             else:
#                 # if (index3 == lon_count - 1) and (index4 < lat_count - 1) and (index4 >= 0):
#                 #     grd_array_inter[index1][index2] = (grd_array[index4][index3] * (
#                 #                 grd_lat[index4 + 1] - inter_lat[index1]) + grd_array[index4 + 1][index3] * (
#                 #                                                    inter_lat[index1] - grd_lat[index4])) / delt_lat
#                 # elif (index3 >= 0) and (index3 < lon_count - 1) and (index4 == lat_count - 1):
#                 #     grd_array_inter[index1][index2] = (grd_array[index4][index3] * (
#                 #                 grd_lon[index3 + 1] - inter_lon[index2]) + grd_array[index4][index3 + 1] * (
#                 #                                                    inter_lon[index2] - grd_lon[index3])) / delt_lon
#                 # elif (index3 == lon_count - 1) and (index4 == lat_count - 1):
#                 #     grd_array_inter[index1][index2] = grd_array[index4][index3]
#                 # else:
#                 #     grd_array_inter[index1][index2] = 0.0
#
#                 if index3 != lon_count - 1 or index4 >= lat_count - 1 or index4 < 0:
#                     if (index3 < 0) or (index3 >= lon_count - 1) or (index4 != lat_count - 1):
#                         if (index3 != lon_count - 1) or (index4 != lat_count - 1):
#                             grd_array_inter[index1][index2] = 0.0
#                         else:
#                             grd_array_inter[index1][index2] = grd_array[index4][index3]
#                     else:
#                         grd_array_inter[index1][index2] = (grd_array[index4][index3] * (grd_lon[index3 + 1] - inter_lon[index2]) +
#                                                            grd_array[index4][index3 + 1] * (inter_lon[index2] - grd_lon[index3])) / delt_lon
#                 else:
#                     grd_array_inter[index1][index2] = (grd_array[index4][index3] * (grd_lat[index4 + 1] - inter_lat[index1]) +
#                                                        grd_array[index4 + 1][index3] * (inter_lat[index1] - grd_lat[index4])) / delt_lat
#     return grd_array_inter