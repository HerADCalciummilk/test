# -*- coding: utf-8 -*-
"""光流反演：由前后降水场估计水平风，供短时效半拉格朗日平流。"""
import math
import numpy as np
from utils.types import PointData, ScatterData, GridData
from proc.spatial_analysis import SpatialAnalisis
from proc import alglib


class OpticalFlow:
    """中心差分梯度 + 窗口稀疏最小二乘，得到 \(u,v\) 格点风。"""
    @staticmethod
    def centra_gradient_x(gd_input):
        """经向中心差分；边界外推。``val`` 形状 ``(yn, xn)``，x 为轴 1。"""
        # val shape (yn, xn): x is axis 1
        grid_data = gd_input.copy_grid_data()
        v = gd_input.val
        gv = grid_data.val
        d = gd_input.lon_interval
        gv[:, 1:-1] = (v[:, 2:] - v[:, :-2]) / (2.0 * d)
        gv[1:-1, 0] = gv[1:-1, 1] + (gv[1:-1, 1] - gv[1:-1, 2])
        gv[1:-1, -1] = gv[1:-1, -2] + (gv[1:-1, -2] - gv[1:-1, -3])
        gv[0, :] = gv[1, :] + (gv[1, :] - gv[2, :])
        gv[-1, :] = gv[-2, :] + (gv[-2, :] - gv[-3, :])
        return grid_data

    @staticmethod
    def centra_gradient_y(gd_input):
        """纬向中心差分；边界外推。``val`` 形状 ``(yn, xn)``，y 为轴 0。"""
        # val shape (yn, xn): y is axis 0
        grid_data = gd_input.copy_grid_data()
        v = gd_input.val
        gv = grid_data.val
        d = gd_input.lat_interval
        gv[1:-1, :] = (v[2:, :] - v[:-2, :]) / (2.0 * d)
        gv[1:-1, 0] = gv[1:-1, 1] + (gv[1:-1, 1] - gv[1:-1, 2])
        gv[1:-1, -1] = gv[1:-1, -2] + (gv[1:-1, -2] - gv[1:-1, -3])
        gv[0, :] = gv[1, :] + (gv[1, :] - gv[2, :])
        gv[-1, :] = gv[-2, :] + (gv[-2, :] - gv[-3, :])
        return grid_data

    @staticmethod
    def _get_wind_from_one_level_optical_flow(gd_qpf_before, gd_qpf_next, min_window, gd_output,
                                                rain_limit=0.1, delta_rain_limit=0.1, num_limit=100):
        num = int(min_window[0] / gd_qpf_before.lon_interval)
        num2 = int(min_window[1] / gd_qpf_before.lat_interval)
        pdx = int(0.5 * num)
        pdy = int(0.5 * num2)
        x_index = []
        y_index = []
        i = int(0.5 * num) + 1
        j = int(0.5 * num2) + 1
        while i <= gd_qpf_before.xn - 1:
            x_index.append(i)
            i += pdx
        while j <= gd_qpf_before.yn - 1:
            y_index.append(j)
            j += pdy

        grid_data = OpticalFlow.centra_gradient_x(gd_qpf_before)
        grid_data2 = OpticalFlow.centra_gradient_y(gd_qpf_before)
        inp1 = OpticalFlow.centra_gradient_x(gd_qpf_next)
        inp2 = OpticalFlow.centra_gradient_y(gd_qpf_next)
        gd_gradient_x = grid_data.copy_grid_data()
        gd_gradient_x.add_val(inp1)
        gd_gradient_x.multi_val(0.5)
        gd_gradient_y = grid_data2.copy_grid_data()
        gd_gradient_y.add_val(inp2)
        gd_gradient_y.multi_val(0.5)
        gd_delta_qpf = gd_qpf_next.copy_grid_data()
        gd_delta_qpf.sub_val(gd_qpf_before)

        u_wnd = {}
        v_wnd = {}
        for j_idx in y_index:
            for i_idx in x_index:
                list3 = []
                list4 = []
                list5 = []
                for k in range(j_idx - pdy, j_idx + pdy + 1):
                    for l in range(i_idx - pdx, i_idx + pdx + 1):
                        if (0 <= l < gd_qpf_before.xn and 0 <= k < gd_qpf_before.yn and
                            abs(gd_delta_qpf.val[k, l]) >= delta_rain_limit and
                            (gd_qpf_before.val[k, l] >= rain_limit or gd_qpf_next.val[k, l] >= rain_limit)):
                            list3.append(gd_gradient_x.val[k, l])
                            list4.append(gd_gradient_y.val[k, l])
                            list5.append(-1.0 * gd_delta_qpf.val[k, l])
                if len(list5) >= num_limit:
                    s = alglib.sparsecreate(len(list3), 2)
                    for m in range(len(list3)):
                        alglib.sparseset(s, m, 0, list3[m])
                        alglib.sparseset(s, m, 1, list4[m])
                    alglib.sparseconverttocrs(s)
                    arr4 = [v for v in list5]
                    state = alglib.linlsqrcreate(len(list5), 2)
                    alglib.linlsqrsetlambdai(state, 0.01)
                    alglib.linlsqrsolvesparse(state, s, arr4)
                    x, rep = alglib.linlsqrresults(state)
                    if rep.terminationtype == 4:
                        db_lon = gd_qpf_before.lon_start + i_idx * gd_qpf_before.lon_interval
                        db_lat = gd_qpf_before.lat_start + j_idx * gd_qpf_before.lat_interval
                        u_wnd[(i_idx, j_idx)] = PointData(db_lon, db_lat, x[0])
                        v_wnd[(i_idx, j_idx)] = PointData(db_lon, db_lat, x[1])

        sd_u = ScatterData([u_wnd[k] for k in u_wnd])
        sd_v = ScatterData([v_wnd[k] for k in v_wnd])

        gd_bg_u = gd_output[0].mesh_val(gd_output[0].lon_start, gd_output[0].lon_end,
                                         gd_output[0].lat_start, gd_output[0].lat_end,
                                         min_window[0], min_window[1])
        gd_bg_v = gd_output[1].mesh_val(gd_output[1].lon_start, gd_output[1].lon_end,
                                         gd_output[1].lat_start, gd_output[1].lat_end,
                                         min_window[0], min_window[1])
        gd_bg_u = SpatialAnalisis.gress_man_interpolation(sd_u, gd_bg_u,
                                                          [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]])
        gd_bg_v = SpatialAnalisis.gress_man_interpolation(sd_v, gd_bg_v,
                                                          [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]])
        gd_output[0] = gd_bg_u.mesh_val(gd_output[0].lon_start, gd_output[0].lon_end,
                                         gd_output[0].lat_start, gd_output[0].lat_end,
                                         gd_output[0].lon_interval, gd_output[0].lat_interval)
        gd_output[1] = gd_bg_v.mesh_val(gd_output[1].lon_start, gd_output[1].lon_end,
                                         gd_output[1].lat_start, gd_output[1].lat_end,
                                         gd_output[1].lon_interval, gd_output[1].lat_interval)

    @staticmethod
    def get_wind_from_optical_flow(gd_qpf_before, gd_qpf_next, min_window, gd_output,
                                    rain_limit=0.1, delta_rain_limit=0.1, num_limit=100):
        """由前后场（或场列表）按 ``min_window`` 多尺度反演风，写入 ``gd_output[0/1]``。"""
        if isinstance(gd_qpf_before, list) and isinstance(gd_qpf_before[0], GridData):
            arr_before = [gd.copy_grid_data() for gd in gd_qpf_before]
            arr_next = [gd.copy_grid_data() for gd in gd_qpf_next]
            for j in range(len(min_window)):
                OpticalFlow._get_wind_from_one_level_optical_flow_multi(
                    arr_before, arr_next, min_window[j], gd_output, rain_limit, delta_rain_limit, num_limit)
        else:
            gd_before2 = gd_qpf_before.copy_grid_data()
            gd_next2 = gd_qpf_next.copy_grid_data()
            for i in range(len(min_window)):
                OpticalFlow._get_wind_from_one_level_optical_flow(
                    gd_before2, gd_next2, min_window[i], gd_output, rain_limit, delta_rain_limit, num_limit)

    @staticmethod
    def _get_wind_from_one_level_optical_flow_multi(gd_qpf_before_list, gd_qpf_next_list, min_window, gd_output,
                                                      rain_limit=0.1, delta_rain_limit=0.1, num_limit=100):
        n_frames = len(gd_qpf_before_list)
        num = int(min_window[0] / gd_qpf_before_list[0].lon_interval)
        num2 = int(min_window[1] / gd_qpf_before_list[0].lat_interval)
        pdx = int(0.5 * num)
        pdy = int(0.5 * num2)
        x_index = []
        y_index = []
        i = int(0.5 * num) + 1
        j = int(0.5 * num2) + 1
        while i <= gd_qpf_before_list[0].xn - 1:
            x_index.append(i)
            i += pdx
        while j <= gd_qpf_before_list[0].yn - 1:
            y_index.append(j)
            j += pdy

        gd_gradient_x_list = []
        gd_gradient_y_list = []
        gd_delta_qpf_list = []
        for k in range(n_frames):
            gx = OpticalFlow.centra_gradient_x(gd_qpf_before_list[k])
            gy = OpticalFlow.centra_gradient_y(gd_qpf_before_list[k])
            gxn = OpticalFlow.centra_gradient_x(gd_qpf_next_list[k])
            gyn = OpticalFlow.centra_gradient_y(gd_qpf_next_list[k])
            ggx = gx.copy_grid_data()
            ggx.add_val(gxn)
            ggx.multi_val(0.5)
            ggy = gy.copy_grid_data()
            ggy.add_val(gyn)
            ggy.multi_val(0.5)
            gdq = gd_qpf_next_list[k].copy_grid_data()
            gdq.sub_val(gd_qpf_before_list[k])
            gd_gradient_x_list.append(ggx)
            gd_gradient_y_list.append(ggy)
            gd_delta_qpf_list.append(gdq)

        u_wnd = {}
        v_wnd = {}
        for j_idx in y_index:
            for i_idx in x_index:
                list3 = []
                list4 = []
                list5 = []
                for l in range(n_frames):
                    for m in range(j_idx - pdy, j_idx + pdy + 1):
                        for n in range(i_idx - pdx, i_idx + pdx + 1):
                            if (0 <= n < gd_qpf_before_list[l].xn and 0 <= m < gd_qpf_before_list[l].yn and
                                abs(gd_delta_qpf_list[l].val[m, n]) >= delta_rain_limit and
                                (gd_qpf_before_list[l].val[m, n] >= rain_limit or gd_qpf_next_list[l].val[m, n] >= rain_limit)):
                                list3.append(gd_gradient_x_list[l].val[m, n])
                                list4.append(gd_gradient_y_list[l].val[m, n])
                                list5.append(-1.0 * gd_delta_qpf_list[l].val[m, n])
                if len(list5) >= num_limit:
                    s = alglib.sparsecreate(len(list3), 2)
                    for m_idx in range(len(list3)):
                        alglib.sparseset(s, m_idx, 0, list3[m_idx])
                        alglib.sparseset(s, m_idx, 1, list4[m_idx])
                    alglib.sparseconverttocrs(s)
                    arr4 = [v for v in list5]
                    state = alglib.linlsqrcreate(len(list5), 2)
                    alglib.linlsqrsetlambdai(state, 0.01)
                    alglib.linlsqrsolvesparse(state, s, arr4)
                    x, rep = alglib.linlsqrresults(state)
                    if rep.terminationtype == 4:
                        db_lon = gd_qpf_before_list[0].lon_start + i_idx * gd_qpf_before_list[0].lon_interval
                        db_lat = gd_qpf_before_list[0].lat_start + j_idx * gd_qpf_before_list[0].lat_interval
                        u_wnd[(i_idx, j_idx)] = PointData(db_lon, db_lat, x[0])
                        v_wnd[(i_idx, j_idx)] = PointData(db_lon, db_lat, x[1])

        sd_u = ScatterData([u_wnd[k] for k in u_wnd])
        sd_v = ScatterData([v_wnd[k] for k in v_wnd])

        gd_bg_u = gd_output[0].mesh_val(gd_output[0].lon_start, gd_output[0].lon_end,
                                         gd_output[0].lat_start, gd_output[0].lat_end,
                                         min_window[0], min_window[1])
        gd_bg_v = gd_output[1].mesh_val(gd_output[1].lon_start, gd_output[1].lon_end,
                                         gd_output[1].lat_start, gd_output[1].lat_end,
                                         min_window[0], min_window[1])
        gd_bg_u = SpatialAnalisis.gress_man_interpolation(sd_u, gd_bg_u,
                                                          [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]])
        gd_bg_v = SpatialAnalisis.gress_man_interpolation(sd_v, gd_bg_v,
                                                          [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]])
        gd_output[0] = gd_bg_u.mesh_val(gd_output[0].lon_start, gd_output[0].lon_end,
                                         gd_output[0].lat_start, gd_output[0].lat_end,
                                         gd_output[0].lon_interval, gd_output[0].lat_interval)
        gd_output[1] = gd_bg_v.mesh_val(gd_output[1].lon_start, gd_output[1].lon_end,
                                         gd_output[1].lat_start, gd_output[1].lat_end,
                                         gd_output[1].lon_interval, gd_output[1].lat_interval)
