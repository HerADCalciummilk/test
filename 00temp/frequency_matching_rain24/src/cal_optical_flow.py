# -- coding: utf-8 --
# @Time : 2025/1/20 15:03
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : cal_opticalFlow.py
# @Software: PyCharm
import numpy as np
import xarray as xr
import meteva.base as meb
from scipy.sparse.linalg import lsqr
from utils.data_proc import creat_M3_grd
from interpolation import GressManInterpolation, mesh_val

class OpticalFlow:

    @staticmethod
    def central_gradient_y(grd: xr.DataArray, res):
        grd_array, array = grd.data.squeeze().copy(), grd.data.squeeze()

        # 计算内部点的梯度
        grd_array[1:-1, 1:-1] = (array[1:-1, 2:] - array[1:-1, :-2]) / (2.0 * res)
        # 处理左边界和右边界
        grd_array[1:-1, 0] = grd_array[1:-1, 1] + (grd_array[1:-1, 1] - grd_array[1:-1, 2])
        grd_array[1:-1, -1] = grd_array[1:-1, -2] + (grd_array[1:-1, -2] - grd_array[1:-1, -3])
        # 处理上边界和下边界
        grd_array[0, :] = grd_array[1, :] + (grd_array[1, :] - grd_array[2, :])
        grd_array[-1, :] = grd_array[-2, :] + (grd_array[-2, :] - grd_array[-3, :])

        return grd_array

    @staticmethod
    def central_gradient_x(grd: xr.DataArray, res):
        grd_array, array = grd.data.squeeze().copy(), grd.data.squeeze()

        # 计算内部点的梯度
        grd_array[1:-1, 1:-1] = (array[2:, 1:-1] - array[:-2, 1:-1]) / (2.0 * res)
        # 处理左边界和右边界
        grd_array[1:-1, 0] = grd_array[1:-1, 1] + (grd_array[1:-1, 1] - grd_array[1:-1, 2])
        grd_array[1:-1, -1] = grd_array[1:-1, -2] + (grd_array[1:-1, -2] - grd_array[1:-1, -3])
        # 处理上边界和下边界
        grd_array[0, :] = grd_array[1, :] + (grd_array[1, :] - grd_array[2, :])
        grd_array[-1, :] = grd_array[-2, :] + (grd_array[-2, :] - grd_array[-3, :])

        return grd_array

    @staticmethod
    def get_opticalflow_single(grd_before, grd_next, min_window, gd_output, rain_limit=0.1,
                                                    delta_rain_limit=0.1, num_limit=100):
        grid_info = meb.basicdata.get_grid_of_data(grd_before)
        delt_lon, delt_lat, lon_count, lat_count = grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat
        start_lon, end_lon, start_lat, end_lat = grid_info.slon, grid_info.elon, grid_info.slat, grid_info.elat

        num_x = int(min_window[0] / delt_lon)
        num_y = int(min_window[1] / delt_lat)
        pdx = int(0.5 * num_x)
        pdy = int(0.5 * num_y)
        x_index = list(range(int(0.5 * num_x) + 1, lon_count, pdx))
        y_index = list(range(int(0.5 * num_y) + 1, lat_count, pdy))

        array1 = OpticalFlow.central_gradient_x(grd_before, delt_lon)
        array2 = OpticalFlow.central_gradient_y(grd_before, delt_lon)
        array3 = OpticalFlow.central_gradient_x(grd_next, delt_lon)
        array4 = OpticalFlow.central_gradient_y(grd_next, delt_lon)
        gd_gradient_x = (array1 + array3) * 0.5
        gd_gradient_y = (array2 + array4) * 0.5
        gd_delta = grd_next.data.squeeze() - grd_before.data.squeeze()

        u_lon, u_lat, u_data = [], [], []
        v_lon, v_lat, v_data = [], [], []
        for j_index in y_index:
            for i_index in x_index:
                list3 = []
                list4 = []
                list5 = []
                num3 = np.arange(j_index - pdy, j_index + pdy + 1)
                num4 = np.arange(i_index - pdx, i_index + pdx + 1)
                cond1 = (0 <= num3) & (num3 < lat_count)
                cond2 = (0 <= num4) & (num4 < lon_count)
                num3 = num3[cond1]
                num4 = num4[cond2]
                xx, yy = np.meshgrid(num3, num4, indexing='ij')
                gdq = gd_delta[xx, yy]
                gqb = grd_before.data.squeeze()[xx, yy]
                gqn = grd_next.data.squeeze()[xx, yy]

                condition = (np.abs(gdq) >= delta_rain_limit) & ((gqb >= rain_limit) | (gqn >= rain_limit))
                list3.extend(gd_gradient_x[xx[condition], yy[condition]])
                list4.extend(gd_gradient_y[xx[condition], yy[condition]])
                list5.extend(-1.0 * gdq[condition])

                if len(list5) >= num_limit:
                    sparsematrix = np.vstack((list4, list3)).T
                    result = lsqr(sparsematrix, list5, damp=0.01)
                    if result[1]:
                        db_lon = start_lon + i_index * delt_lon
                        db_lat = start_lat + j_index * delt_lat
                        u_lon.append(db_lon)
                        u_lat.append(db_lat)
                        u_data.append(result[0][0])
                        v_lon.append(db_lon)
                        v_lat.append(db_lat)
                        v_data.append(result[0][1])

        sd_input_data1 = creat_M3_grd(u_lon, u_lat, u_data)
        sd_input_data2 = creat_M3_grd(v_lon, v_lat, v_data)

        gdBackgroundData1 = mesh_val(gd_output[1], [start_lon, end_lon, start_lat, end_lat, min_window[1]])
        gdBackgroundData2 = mesh_val(gd_output[0], [start_lon, end_lon, start_lat, end_lat, min_window[1]])

        distanceLimits = [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]]
        gridData2 = GressManInterpolation(sd_input_data1, gdBackgroundData2, distanceLimits)
        gridData3 = GressManInterpolation(sd_input_data2, gdBackgroundData1, distanceLimits)
        gd_output[0] = mesh_val(gridData2, [start_lon, end_lon, start_lat, end_lat, delt_lon])
        gd_output[1] = mesh_val(gridData3, [start_lon, end_lon, start_lat, end_lat, delt_lon])


    @staticmethod
    def get_opticalflow_multiple(grd_before, grd_next, min_window, gd_output, rain_limit=0.1,
                                                      delta_rain_limit=0.1, num_limit=100):

        grid_info = meb.basicdata.get_grid_of_data(grd_before[0])
        delt_lon, delt_lat, lon_count, lat_count = grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat
        start_lon, end_lon, start_lat, end_lat = grid_info.slon, grid_info.elon, grid_info.slat, grid_info.elat

        num_x = int(min_window[0] / delt_lon)
        num_y = int(min_window[1] / delt_lat)
        pdx = int(0.5 * num_x)
        pdy = int(0.5 * num_y)
        x_index = list(range(int(0.5 * num_x) + 1, lon_count, pdx))
        y_index = list(range(int(0.5 * num_y) + 1, lat_count, pdy))

        array1 = np.array([OpticalFlow.central_gradient_x(gd, delt_lon) for gd in grd_before])
        array2 = np.array([OpticalFlow.central_gradient_y(gd, delt_lon) for gd in grd_before])
        array3 = np.array([OpticalFlow.central_gradient_x(gd, delt_lon) for gd in grd_next])
        array4 = np.array([OpticalFlow.central_gradient_y(gd, delt_lon) for gd in grd_next])
        gd_gradient_x = (array1 + array3) * 0.5
        gd_gradient_y = (array2 + array4) * 0.5
        gd_delta = [grd_next[i].data.squeeze() - grd_before[i].data.squeeze() for i in range(len(grd_before))]

        u_lon, u_lat, u_data = [], [], []
        v_lon, v_lat, v_data = [], [], []
        for j_index in y_index:
            for i_index in x_index:
                list3 = []
                list4 = []
                list5 = []
                for n in range(len(grd_before)):
                    num3 = np.arange(j_index - pdy, j_index + pdy + 1)
                    num4 = np.arange(i_index - pdx, i_index + pdx + 1)
                    cond1 = (0 <= num3) & (num3 < lat_count)
                    cond2 = (0 <= num4) & (num4 < lon_count)
                    num3 = num3[cond1]
                    num4 = num4[cond2]
                    xx, yy = np.meshgrid(num3, num4, indexing='ij')
                    gdq = gd_delta[n][xx, yy]
                    gqb = grd_before[n].data.squeeze()[xx, yy]
                    gqn = grd_next[n].data.squeeze()[xx, yy]

                    condition = (np.abs(gdq) >= delta_rain_limit) & ((gqb >= rain_limit) | (gqn >= rain_limit))
                    list3.extend(gd_gradient_x[n][xx[condition], yy[condition]])
                    list4.extend(gd_gradient_y[n][xx[condition], yy[condition]])
                    list5.extend(-1.0 * gdq[condition])

                if len(list5) >= num_limit:
                    sparsematrix = np.vstack((list4, list3)).T
                    result = lsqr(sparsematrix, list5, damp=0.01)
                    if result[1]:
                        db_lon = start_lon + i_index * delt_lon
                        db_lat = start_lat + j_index * delt_lat
                        u_lon.append(db_lon)
                        u_lat.append(db_lat)
                        u_data.append(result[0][0])
                        v_lon.append(db_lon)
                        v_lat.append(db_lat)
                        v_data.append(result[0][1])

        sd_input_data1 = creat_M3_grd(u_lon, u_lat, u_data)
        sd_input_data2 = creat_M3_grd(v_lon, v_lat, v_data)

        # grid0 = meb.grid([start_lon, end_lon - min_window[0], min_window[0]],
        #                  [start_lat, end_lat - min_window[1], min_window[1]])
        # gdBackgroundData2 = meb.grid_data(grid0)
        # gdBackgroundData1 = meb.grid_data(grid0)
        gdBackgroundData1 = mesh_val(gd_output[1], [start_lon, end_lon, start_lat, end_lat, min_window[1]])
        gdBackgroundData2 = mesh_val(gd_output[0], [start_lon, end_lon, start_lat, end_lat, min_window[1]])

        distanceLimits = [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]]
        gridData2 = GressManInterpolation(sd_input_data1, gdBackgroundData2, distanceLimits)
        gridData3 = GressManInterpolation(sd_input_data2, gdBackgroundData1, distanceLimits)
        gd_output[0] = mesh_val(gridData2, [start_lon, end_lon, start_lat, end_lat, delt_lon])
        gd_output[1] = mesh_val(gridData3, [start_lon, end_lon, start_lat, end_lat, delt_lon])


    @staticmethod
    def get_optical_flow(grd_before, grd_next, min_window, gd_output, rain_limit=0.1, delta_rain_limit=0.1,
                                   num_limit=100):
        if isinstance(grd_before, xr.DataArray):
            for i in range(len(min_window)):
                OpticalFlow.get_opticalflow_single(grd_before, grd_next, min_window[i],
                                                                        gd_output, rain_limit, delta_rain_limit, num_limit)
        elif isinstance(grd_before, list) or isinstance(grd_before, np.ndarray):
            for j in range(len(min_window)):
                OpticalFlow.get_opticalflow_multiple(grd_before, grd_next, min_window[j], gd_output,
                                                                          rain_limit, delta_rain_limit, num_limit)

class Lagrangian:
    @staticmethod
    def simple_semi_lagrangian_in_angle(gd_u_wnd: xr.DataArray, gd_v_wnd: xr.DataArray, gd_rain: xr.DataArray, delta_time):
        gd_output = gd_rain.copy()
        grid_info = meb.basicdata.get_grid_of_data(gd_output)
        delt_lon, delt_lat, lon_count, lat_count = grid_info.dlon, grid_info.dlat, grid_info.nlon, grid_info.nlat
        start_lon, end_lon, start_lat, end_lat = grid_info.slon, grid_info.elon, grid_info.slat, grid_info.elat

        u_array, v_array, tp_array = gd_u_wnd.data.squeeze(), gd_v_wnd.data.squeeze(), gd_rain.data.squeeze()
        lon_array, lat_array = gd_output.lon.to_numpy(), gd_output.lat.to_numpy()

        # correct_array = tp_array.copy()
        # for j in range(lat_count):
        #     for i in range(lon_count):
        #         num1 = start_lon + i * delt_lon
        #         num2 = start_lat + j * delt_lat
        #         num3 = u_array[j, i] * delta_time
        #         num4 = num1 - num3
        #         num5 = num2 - v_array[j, i] * delta_time
        #         index1 = int((num4 + 1E-05 - start_lon) / delt_lon)
        #         index2 = int((num5 + 1E-05 - start_lat) / delt_lat)
        #         if (index1 >= 0) & (index1 < lon_count - 1) & (index2 >= 0) & (index2 < lat_count - 1):
        #             num6 = ((lon_array[index1 + 1] - num4) * tp_array[index2][index1] + (num4 - lon_array[index1]) * tp_array[index2][index1 + 1]) / delt_lon
        #             num7 = ((lon_array[index1 + 1] - num4) * tp_array[index2 + 1][index1] + (num4 - lon_array[index1]) * tp_array[index2 + 1][index1 + 1]) / delt_lon
        #             num8 = ((lat_array[index2 + 1] - num5) * num6 + (num5 - lat_array[index2]) * num7) / delt_lat
        #             correct_array[j][i] = num8


        lon_grid, lat_grid = np.meshgrid(lon_array, lat_array)

        # 计算偏移
        lon_offset = lon_grid - u_array * delta_time
        lat_offset = lat_grid - v_array * delta_time

        # 计算索引
        index1 = np.clip(((lon_offset - start_lon) / delt_lon).astype(int), 0, lon_count - 2)
        index2 = np.clip(((lat_offset - start_lat) / delt_lat).astype(int), 0, lat_count - 2)

        # 计算权重并进行双线性插值
        lon1_weight = (lon_array[index1 + 1] - lon_offset) / delt_lon
        lon2_weight = (lon_offset - lon_array[index1]) / delt_lon
        lat1_weight = (lat_array[index2 + 1] - lat_offset) / delt_lat
        lat2_weight = (lat_offset - lat_array[index2]) / delt_lat

        # 双线性插值的四个邻近点
        tp_00 = tp_array[index2, index1]
        tp_01 = tp_array[index2, index1 + 1]
        tp_10 = tp_array[index2 + 1, index1]
        tp_11 = tp_array[index2 + 1, index1 + 1]
        correct_array = (lon1_weight * (lat1_weight * tp_00 + lat2_weight * tp_10) +
                         lon2_weight * (lat1_weight * tp_01 + lat2_weight * tp_11))

        gd_output.data = [[[[correct_array]]]]
        return gd_output