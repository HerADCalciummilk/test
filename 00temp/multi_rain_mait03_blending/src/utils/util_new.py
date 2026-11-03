# -*- coding: UTF-8 -*-
"""
MAIT 3h 数值核：频率匹配、Cressman、TS、格点/站点容器、并行切分。

与原 ``mait_3h/src/util_new.py`` 算法一致。频率匹配分位排序前对样本加
``U(0, 10^{-3})`` 扰动（原算法即如此，同输入两次运行不必逐 bit 相同）。
"""
# @Software : python
import os
import struct

import meteva_base as meb
import meteva.method as mem
from copy import deepcopy

import numpy as np
import random
import pandas as pd
# from tqdm import tqdm
import xarray as xr
import logging
from multiprocessing import Pool

data0_str = 'data0'


def copy_data(data):
    """深拷贝站点 / 格点对象，避免订正时改写入参。"""
    new_data = deepcopy(data)
    return new_data


class MetevaFrequencyMatch():
    """分位频率匹配：由参考场与模式场建立级映射，再分段线性订正。"""

    @staticmethod
    def get_model_level(model_data, fact_data, fact_level, fact_level_limit=None):
        """对参考/模式样本排序（含 \(U(0,10^{-3})\) 扰动），按 ``fact_level`` 分位插出模式阈值。"""
        ft_dy_n = len(fact_data)
        md_dy_n = len(model_data)

        lt_ft = []
        lt_md = []

        if isinstance(model_data[0], pd.DataFrame):
            for i in range(ft_dy_n):
                fact_data_array = fact_data[i][data0_str].to_numpy()

                for j in range(len(fact_data[i])):
                    data1 = fact_data_array[j]

                    lt_ft.append(data1 + random.random() / 1000)  # 原算法扰动，避免同分位黏连
                    # lt_ft.append(data1 + 0.885314533614836 / 1000)
                fact_data[i][data0_str] = fact_data_array

            for k in range(md_dy_n):
                model_data_array = model_data[k][data0_str].to_numpy()
                for l in range(len(model_data[k])):
                    data2 = model_data_array[l]
                    lt_md.append(data2 + random.random() / 1000)  # 同上，模式样本扰动
                    # lt_md.append(data2 + 0.885314533614836 / 1000)
                model_data[k][data0_str] = model_data_array

        lt_ft = sorted(lt_ft)
        lt_md = sorted(lt_md)

        level_n = len(fact_level)
        model_level = [[0.0] * level_n, [0.0] * level_n]

        for i_level in range(len(fact_level)):
            if not fact_level_limit:
                if (fact_level[i_level] >= lt_ft[-1] or fact_level[i_level] < lt_ft[0]):
                    model_level[0][i_level] = 0.0
                    model_level[1][i_level] = fact_level[i_level]
                else:
                    for i in range(len(lt_ft) - 1):
                        if (lt_ft[i] <= fact_level[i_level] < lt_ft[i + 1]):
                            fp = int((i + 1.0) / len(lt_ft) * len(lt_md)) - 1
                            if fp < 0 or fp >= len(lt_md) - 1:
                                model_level[0][i_level] = 0.0
                                model_level[1][i_level] = fact_level[i_level]
                            else:
                                model_level[0][i_level] = 1.0
                                model_level[1][i_level] = (lt_md[fp] + (lt_md[fp + 1] - lt_md[fp]) *
                                                           (fact_level[i_level] - lt_ft[i]) /
                                                           (lt_ft[i + 1] - lt_ft[i]))
            else:
                if (fact_level_limit) < 0.5 * (len(lt_ft) - 1):
                    if (fact_level[i_level] >= lt_ft[-1 - fact_level_limit] or fact_level[i_level] < lt_ft[
                        fact_level_limit]):
                        model_level[0][i_level] = 0.0
                        model_level[1][i_level] = fact_level[i_level]
                    else:
                        for i in range([fact_level_limit, len(lt_ft) - 1 - fact_level_limit]):
                            if fact_level[i_level] >= lt_ft[i] and fact_level[i_level] < lt_ft[i + 1]:
                                fp = int((i + 1.0) / len(lt_ft) * len(lt_md)) - 1
                                if fp < 0 or fp >= len(lt_md) - 1:
                                    model_level[0][i_level] = 0.0
                                    model_level[1][i_level] = fact_level[i_level]
                                else:
                                    model_level[0][i_level] = 1.0
                                    model_level[1][i_level] = (lt_md[fp] + (lt_md[fp + 1] - lt_md[fp]) *
                                                               (fact_level[i_level] - lt_ft[i]) /
                                                               (lt_ft[i + 1] - lt_ft[i]))
                else:
                    model_level[0][i_level] = 0.0
                    model_level[1][i_level] = fact_level[i_level]

        return model_level

    @staticmethod
    def get_used_model_level(model_data, fact_data, fact_level, fact_level_limit=None):
        """同 ``get_model_level``，但只返回有效（可映射）的级对。"""


        ft_dy_n = len(fact_data)
        md_dy_n = len(model_data)

        lt_ft = []
        lt_md = []

        if isinstance(model_data[0],StationDataArray):

            for i in range(ft_dy_n):
                for j in range(len(fact_data[i].id)):
                    lt_ft.append(fact_data[i].data[j] + random.random() / 1000)
                    # lt_ft.append(fact_data[i].data[j] + 0.885314533614836 / 1000)

            for k in range(md_dy_n):
                for l in range(len(model_data[k].id)):
                    lt_md.append(model_data[k].data[l] + random.random() / 1000)
                    # lt_md.append(model_data[k].data[l] + 0.885314533614836 / 1000)

        elif isinstance(model_data[0],pd.DataFrame):

            for i in range(ft_dy_n):
                for j in range(len(fact_data[i])):
                    # lt_ft.append(fact_data[i].data[j] + random.random() / 1000)
                    lt_ft.append(fact_data[i][data0_str].to_numpy()[j] + random.random() / 1000)

            for k in range(md_dy_n):
                for l in range(len(model_data[k])):
                    # lt_md.append(model_data[k].data[l] + random.random() / 1000)
                    lt_md.append(model_data[k][data0_str].to_numpy()[l] + random.random() / 1000)

        elif isinstance(model_data[0], float):
            for i in range(ft_dy_n):
                # lt_ft.append(fact_data[i] + 0.885314533614836 / 1000)
                lt_ft.append(fact_data[i] + random.random() / 1000)
                # lt_ft.append(fact_data[i])

            for j in range(md_dy_n):
                # lt_md.append(model_data[j] + 0.885314533614836 / 1000)
                lt_md.append(model_data[j] + random.random() / 1000)
                # lt_md.append(model_data[j])

        lt_ft = sorted(np.array(lt_ft))
        lt_md = sorted(np.array(lt_md))

        level_n = len(fact_level)
        model_level = [[0.0] * level_n, [0.0] * level_n]

        for i_level in range(len(fact_level)):
            if not fact_level_limit:
                if (fact_level[i_level] >= lt_ft[-1] or fact_level[i_level] < lt_ft[0]):
                    model_level[0][i_level] = 0.0
                    model_level[1][i_level] = fact_level[i_level]
                else:
                    for i in range(len(lt_ft) - 1):
                        if fact_level[i_level] >= lt_ft[i] and fact_level[i_level] < lt_ft[i + 1]:
                            fp = int((i + 1.0) / len(lt_ft) * len(lt_md)) - 1
                            if fp < 0 or fp >= len(lt_md) - 1:
                                model_level[0][i_level] = 0.0
                                model_level[1][i_level] = fact_level[i_level]
                            else:
                                model_level[0][i_level] = 1.0
                                model_level[1][i_level] = (lt_md[fp] + (lt_md[fp + 1] - lt_md[fp]) *
                                                           (fact_level[i_level] - lt_ft[i]) /
                                                           (lt_ft[i + 1] - lt_ft[i]))
            else:
                if (float)(fact_level_limit) < 0.5 * (float)(len(lt_ft) - 1):
                    if (fact_level[i_level] >= lt_ft[-1 - fact_level_limit] or fact_level[i_level] < lt_ft[
                        fact_level_limit]):
                        model_level[0][i_level] = 0.0
                        model_level[1][i_level] = fact_level[i_level]
                    else:
                        for i in range([fact_level_limit, len(lt_ft) - 1 - fact_level_limit]):
                            if fact_level[i_level] >= lt_ft[i] and fact_level[i_level] < lt_ft[i + 1]:
                                fp = int((i + 1.0) / len(lt_ft) * len(lt_md)) - 1
                                if fp < 0 or fp >= len(lt_md) - 1:
                                    model_level[0][i_level] = 0.0
                                    model_level[1][i_level] = fact_level[i_level]
                                else:
                                    model_level[0][i_level] = 1.0
                                    model_level[1][i_level] = (lt_md[fp] + (lt_md[fp + 1] - lt_md[fp]) * (
                                            fact_level[i_level] - lt_ft[i]) / (lt_ft[i + 1] - lt_ft[i]))
        used_list = []
        used_fact_list = []

        for m in range(level_n):
            if abs(model_level[0][m] - 0.0) > 1e-5:
                used_list.append(model_level[1][m])
                used_fact_list.append(fact_level[m])

        return [used_list, used_fact_list]

    @staticmethod
    def correct_model_data(model_data, fact_level, model_level):
        """按级对分段线性订正站点 DataFrame / ``StationDataArray`` / ``GridData``。"""
        if isinstance(model_data, StationDataArray):
            model_data = MetevaFrequencyMatch.correct_model_data_scatter(model_data, fact_level, model_level)
        if isinstance(model_data, pd.DataFrame):
            model_data = MetevaFrequencyMatch.correct_model_data_scatter_df(model_data, fact_level, model_level)
        elif isinstance(model_data, GridData):
            model_data = MetevaFrequencyMatch.correct_model_data_grid(model_data, fact_level, model_level)
        else:
            raise Exception("Model Data format incorrect!.")
        return model_data

    @staticmethod
    def correct_model_data_scatter(model_data, fact_level, model_level):
        scatter_data = copy_data(model_data)
        num = len(fact_level)
        num2 = len(scatter_data.id)
        if num > 0:
            for i in range(num2):
                if model_data.data[i] < model_level[0]:
                    if model_level[0] == 0.0:
                        scatter_data.data[i] = 0.0
                    else:
                        scatter_data.data[i] = model_data.data[i] * fact_level[0] / model_level[0]
                elif model_data.data[i] < model_level[num - 1]:
                    for j in range(num - 1):
                        if model_data.data[i] >= model_level[j] and model_data.data[i] < model_level[j + 1]:
                            scatter_data.data[i] = fact_level[j] + (fact_level[j + 1] - fact_level[j]) * (
                                    model_data.data[i] - model_level[j]) / (model_level[j + 1] - model_level[j])
                elif model_level[num - 1] == 0.0:
                    scatter_data.data[i] = 0.0
                else:
                    scatter_data.data[i] = model_data.data[i] * fact_level[num - 1] / model_level[num - 1]
        return scatter_data

    @staticmethod
    def correct_model_data_scatter_df(model_data, fact_level, model_level):
        scatter_data = copy_data(model_data)
        model_data_array = model_data[data0_str].to_numpy()
        scatter_data_array = scatter_data[data0_str].to_numpy()

        num = len(fact_level)
        num2 = len(scatter_data)
        if num > 0:
            for i in range(num2):
                if model_data_array[i] < model_level[0]:
                    if model_level[0] == 0.0:
                        scatter_data_array[i] = 0.0
                    else:
                        scatter_data_array[i] = model_data_array[i] * fact_level[0] / model_level[0]
                elif model_data_array[i] < model_level[num - 1]:
                    for j in range(num - 1):
                        if model_data_array[i] >= model_level[j] and model_data_array[i] < model_level[
                            j + 1]:
                            scatter_data_array[i] = fact_level[j] + (fact_level[j + 1] - fact_level[j]) * (
                                    model_data_array[i] - model_level[j]) / (
                                                            model_level[j + 1] - model_level[j])
                elif model_level[num - 1] == 0.0:
                    scatter_data_array[i] = 0.0
                else:
                    scatter_data_array[i] = model_data_array[i] * fact_level[num - 1] / model_level[
                        num - 1]
        scatter_data[data0_str] = scatter_data_array
        return scatter_data

    @staticmethod
    def correct_model_data_grid(model_data, fact_level, model_level):
        grid_data = copy_data(model_data)
        num = len(fact_level)
        if num > 0:
            for i in range(grid_data.yn):
                for j in range(grid_data.xn):
                    if model_data.data[j][i] < model_level[0]:
                        if model_level[0] == 0.0:
                            grid_data.data[j][i] = 0.0
                        else:
                            grid_data.data[j][i] = model_data.data[j][i] * fact_level[0] / model_level[0]
                    elif model_data.data[j][i] < model_level[num - 1]:
                        for k in range(num - 1):
                            if model_data.data[j][i] >= model_level[k] and model_data.data[j][i] < model_level[k + 1]:
                                grid_data.data[j][i] = fact_level[k] + (fact_level[k + 1] - fact_level[k]) * (
                                        model_data.data[j][i] - model_level[k]) / (
                                                               model_level[k + 1] - model_level[k])
                    elif model_level[num - 1] == 0.0:
                        grid_data.data[j][i] = 0.0
                    else:
                        grid_data.data[j][i] = model_data.data[j][i] * fact_level[num - 1] / model_level[num - 1]
        return grid_data

    @staticmethod
    def get_used_model_level_and_extend(model_data, fact_data, fact_level):
        used_model_level = MetevaFrequencyMatch.get_used_model_level(model_data, fact_data, fact_level)
        if len(used_model_level[0]) == 0:
            return used_model_level

        if len(used_model_level[0]) < len(fact_level):
            array = copy_data(used_model_level)
            for j in range(len(fact_level)):
                if fact_level[j] > used_model_level[1][-1]:
                    array[0][-1] = max(array[0][-2] * 2.0, fact_level[j])
                    array[1][-1] = fact_level[j]
                    break

            return array
        return used_model_level


class MetevaSpatialAnalisis:
    """降水 Cressman 客观分析：单步订正与多半径循环。"""

    @staticmethod
    def cressman_one_step_interpolation_for_rain(
            sd_input_data, gd_background_data, distance_limit, number_limit=1, smooth=0.001,
            power_param=2.0, rain_limit=0.01):
        """

        :param sd_input_data: 站点数据
        :param gd_background_data: 格点数据
        :param distance_limit:
        :param number_limit:
        :param smooth:
        :param power_param:
        :param rain_limit:
        :return:
        """
        # 取出站点经纬度
        sta_lon = sd_input_data.lon
        sta_lat = sd_input_data.lat
        sta_data = sd_input_data.data
        sta_data0 = np.zeros_like(sta_data)

        # 取出格点经纬度
        grid_lon = gd_background_data.lon
        grid_lat = gd_background_data.lat
        grid_data = gd_background_data.data
        grid_lon_interval = gd_background_data.lon_interval
        grid_lat_interval = gd_background_data.lat_interval
        grid_lon_start = gd_background_data.lon_start
        grid_lat_start = gd_background_data.lat_start
        grid_xn = gd_background_data.xn
        grid_yn = gd_background_data.yn
        grid_data0 = np.zeros_like(grid_data)
        # 站点数据
        sta_num = len(sta_lon)
        # 站点数据
        sd_from_background_data = sta_data0
        sd_delta_input_data_data = sta_data

        influence_grid = int(distance_limit / grid_lon_interval)

        # for n in tqdm(range(sta_num)):
        for n in range(sta_num):
            ix = ((sta_lon[n] + 1e-5 - grid_lon_start) / grid_lon_interval).astype(int)
            iy = ((sta_lat[n] + 1e-5 - grid_lat_start) / grid_lat_interval).astype(int)

            ix_start = np.maximum(ix - influence_grid, 0)
            ix_end = np.minimum(ix + influence_grid, grid_xn - 1)
            iy_start = np.maximum(iy - influence_grid, 0)
            iy_end = np.minimum(iy + influence_grid, grid_yn - 1)

            lon_distance = grid_lon[ix_start:ix_end + 1] - sta_lon[n]
            lat_distance = grid_lat[iy_start:iy_end + 1] - sta_lat[n]
            total_distance = np.sqrt(lon_distance[:, np.newaxis] ** 2 + lat_distance ** 2)
            mask = total_distance <= distance_limit
            single_weight = 1.0 / np.power((total_distance[mask] + smooth), power_param)
            val_tmp = np.sum(single_weight * grid_data[ix_start:ix_end + 1, iy_start:iy_end + 1][mask])
            total_weight = np.sum(single_weight)
            sd_from_background_data[n] = val_tmp / total_weight if total_weight >= 1e-05 else sta_data[n]

        # 站点数据相减
        sd_delta_input_data_data = sd_delta_input_data_data - sd_from_background_data
        # 格点
        gd_output_data = copy_data(gd_background_data)
        gd_weight_data = copy_data(gd_background_data)
        gd_points_data_data = grid_data0

        gd_output_data.clear_to_num(0.0)
        gd_weight_data.clear_to_num(0.0)

        # for n in tqdm(range(sta_num)):
        for n in range(sta_num):
            ix = ((sta_lon[n] - grid_lon_start) / grid_lon_interval).astype(int)
            iy = ((sta_lat[n] - grid_lat_start) / grid_lat_interval).astype(int)
            ix_start = max(0, ix - influence_grid)
            ix_end = min(grid_xn - 1, ix + influence_grid)
            iy_start = max(0, iy - influence_grid)
            iy_end = min(grid_yn - 1, iy + influence_grid)

            lon_distance = grid_lon[ix_start:ix_end + 1][:, np.newaxis] - sta_lon[n]
            lat_distance = grid_lat[iy_start:iy_end + 1] - sta_lat[n]
            total_distance = np.sqrt(lon_distance ** 2 + lat_distance ** 2)
            mask = total_distance <= distance_limit
            single_weight = 1.0 / np.power(total_distance[mask] + smooth, power_param)

            gd_output_data.data[ix_start:ix_end + 1, iy_start:iy_end + 1][mask] += single_weight * \
                                                                                   sd_delta_input_data_data[
                                                                                       n]
            gd_weight_data.data[ix_start:ix_end + 1, iy_start:iy_end + 1][mask] += single_weight
            gd_points_data_data[ix_start:ix_end + 1, iy_start:iy_end + 1][mask] += 1.0

        update_condition = (gd_weight_data.data >= 1e-5) & (gd_points_data_data >= number_limit)
        gd_output_data_update = gd_output_data.data / gd_weight_data.data + grid_data

        gd_output_data.data[update_condition] = np.where(
            gd_output_data_update[update_condition] <= rain_limit,
            grid_data[update_condition],
            gd_output_data_update[update_condition]
        )

        gd_output_data.data[~update_condition] = grid_data[~update_condition]
        return gd_output_data

    @staticmethod
    def gressman_interpolation_for_rain(sd_input_data, gd_background_data, distance_limits,
                                        num_limit=1, smooth=0.001, power_param=2,
                                        rain_limit=0.01):
        """按 ``distance_limits`` 由大到小多次 Cressman，每步以上一步场为背景。"""
        gd_output_data_tmp = gd_background_data
        for n in range(len(distance_limits)):
            gd_output_data_tmp = MetevaSpatialAnalisis.cressman_one_step_interpolation_for_rain(sd_input_data,
                                                                                                gd_output_data_tmp,
                                                                                                distance_limits[n],
                                                                                                num_limit,
                                                                                                smooth, power_param,
                                                                                                rain_limit)
        return gd_output_data_tmp


def bilinear_interpolation_from_grid_data(sd_reference, input_data, db_undef=0.0):
    """格点场双线性插到站点；越界填 ``db_undef``。"""
    # 站点数据
    sta_n = len(sd_reference.id)
    # 格点数据 input_data
    for n in range(sta_n):
        ix = int((sd_reference.lon[n] + 0.00001 - input_data.lon_start) / input_data.lon_interval)
        jy = int((sd_reference.lat[n] + 0.00001 - input_data.lat_start) / input_data.lat_interval)
        if (ix >= 0) and (ix < input_data.xn - 1) and (jy >= 0) and (jy < input_data.yn - 1):
            temp1 = ((input_data.data[ix][jy] * (input_data.lon[ix + 1] - sd_reference.lon[n]) +
                      input_data.data[ix + 1][jy] * (sd_reference.lon[n] - input_data.lon[ix])) /
                     input_data.lon_interval)
            temp2 = ((input_data.data[ix][jy + 1] * (input_data.lon[ix + 1] - sd_reference.lon[n]) +
                      input_data.data[ix + 1][jy + 1] * (sd_reference.lon[n] - input_data.lon[ix])) /
                     input_data.lon_interval)
            temp = ((temp1 * (input_data.lat[jy + 1] - sd_reference.lat[n]) +
                     temp2 * (sd_reference.lat[n] - input_data.lat[jy])) /
                    input_data.lat_interval)
            sd_reference.data[n] = temp
        else:
            sd_reference.data[n] = db_undef
    return sd_reference


def read_float_val_from_bin(input_file_path, lon_start, lon_end, lat_start, lat_end, d_lon, d_lat):
    """按网格尺寸读 float32 掩膜二进制（行优先纬度、列优先经度）。"""
    _xn = int(round((lon_end + 0.00001 - lon_start) / d_lon)) + 1
    _yn = int(round((lat_end + 0.00001 - lat_start) / d_lat)) + 1
    _val = [[0.0 for j in range(_yn)] for i in range(_xn)]
    _val = np.asarray(_val)
    with open(input_file_path, 'rb') as input_file:
        for j in range(_yn):
            for i in range(_xn):
                _val[i][j] = struct.unpack('f', input_file.read(4))[0]
    return _val, _xn, _yn


class GridData():
    """Micaps4 格点容器（经纬、间隔、二维 ``data``），供 Cressman / 频率匹配使用。"""

    def __init__(self, file):
        self.file = file
        self.read_griddata_from_micaps4()

    @property
    def data(self):
        return self._data

    @property
    def lon(self):
        return self._lons

    @property
    def lat(self):
        return self._lats

    @property
    def lon_start(self):
        return self._lon_start

    @property
    def lon_end(self):
        return self._lon_end

    @property
    def lat_start(self):
        return self._lat_start

    @property
    def lat_end(self):
        return self._lat_end

    @property
    def xn(self):
        return self._xn

    @property
    def yn(self):
        return self._yn

    @property
    def lon_interval(self):
        return self._lon_interval

    @property
    def lat_interval(self):
        return self._lat_interval

    def read_griddata_from_micaps4(self):
        ds = meb.read_griddata_from_micaps4(self.file)
        self._lons = ds.lon.data
        self._lats = ds.lat.data
        self._data = ds.data[0][0][0][0].T
        self._lon_start = self._lons[0]
        self._lon_end = self._lons[-1]
        self._lat_start = self._lats[0]
        self._lat_end = self._lats[-1]
        self._xn = len(self._lons)
        self._yn = len(self._lats)
        self._lon_interval = round(self._lons[1] - self._lons[0], 2)
        self._lat_interval = round(self._lats[1] - self._lats[0], 2)
        del ds

    def meteva_grid2array(self, ds):
        self._lons = ds.lon.data
        self._lats = ds.lat.data
        self._data = ds.lat.data[0][0][0][0].T
        self._lon_start = self._lons[0]
        self._lon_end = self._lons[-1]
        self._lat_start = self._lats[0]
        self._lat_end = self._lats[-1]
        self._xn = len(self._lons)
        self._yn = len(self._lats)
        self._lon_interval = round(self._lons[1] - self._lons[0], 2)
        self._lat_interval = round(self._lats[1] - self._lats[0], 2)
        del ds

    def array2meteva_grid(self, array):
        grid = meb.grid([self.lon_start, self.lon_end, self.lon_interval],
                        [self.lat_start, self.lat_end, self.lat_interval])
        data = array.T
        slon = grid.slon
        dlon = grid.dlon
        slat = grid.slat
        dlat = grid.dlat
        nlon = grid.nlon
        nlat = grid.nlat
        # 通过起始经纬度和格距计算经纬度格点数
        lon = np.arange(nlon) * dlon + slon
        lat = np.arange(nlat) * dlat + slat
        dt_str = grid.gtime[2]
        if dt_str.find("m") >= 0:
            dt_str = dt_str.replace("m", "min")

        times = pd.date_range(grid.stime, grid.etime, freq=dt_str)

        ntime = len(times)
        # 根据timedelta的格式，算出ndt次数和gds时效列表

        ndt = len(grid.dtimes)
        gdt_list = grid.dtimes

        level_list = grid.levels
        nlevel_list = len(level_list)

        member_list = grid.members
        nmember = len(member_list)
        if data is None:
            data = np.zeros((nmember, nlevel_list, ntime, ndt, nlat, nlon))
        else:
            data = data.reshape(nmember, nlevel_list, ntime, ndt, nlat, nlon)

        grd = (xr.DataArray(data, coords={'member': member_list, 'level': level_list, 'time': times, 'dtime': gdt_list,
                                          'lat': lat, 'lon': lon},
                            dims=['member', 'level', 'time', 'dtime', 'lat', 'lon']))

        grd.name = data0_str
        return grd

    def smooth_9(self, ct_num):
        val_tmp = np.zeros((self._xn, self._yn))
        for ct in range(ct_num):
            for j in range(1, self._yn - 1):
                for i in range(1, self._xn - 1):
                    tmp1 = (0.25 * self.data[i - 1][j + 1] + 0.5 * self.data[i][j + 1] +
                            0.25 * self.data[i + 1][j + 1])
                    tmp2 = (0.25 * self.data[i - 1][j] + 0.5 * self.data[i][j] +
                            0.25 * self.data[i + 1][j])
                    tmp3 = (0.25 * self.data[i - 1][j - 1] + 0.5 * self.data[i][j - 1] +
                            0.25 * self.data[i + 1][j - 1])
                    tmp = 0.25 * tmp1 + 0.5 * tmp2 + 0.25 * tmp3
                    val_tmp[i][j] = tmp

            for j in range(1, self._yn - 1):
                val_tmp[0][j] = val_tmp[1][j] + (val_tmp[1][j] - val_tmp[2][j])
                val_tmp[self._xn - 1][j] = (
                        val_tmp[self._xn - 2][j] + (val_tmp[self._xn - 2][j] - val_tmp[self._xn - 3][j]))

            for i in range(self._xn):
                val_tmp[i][0] = val_tmp[i][1] + (val_tmp[i][1] - val_tmp[i][2])
                val_tmp[i][self._yn - 1] = (val_tmp[i][self._yn - 2] +
                                            (val_tmp[i][self._yn - 2] - val_tmp[i][self._yn - 3]))

            for j in range(self._yn):
                for i in range(self._xn):
                    self.data[i][j] = val_tmp[i][j]
                    if self.data[i][j] <= 0.0:
                        self.data[i][j] = 0.0
        self._data = self.data

    def multi_val(self, input):
        self._data = self.data * input

    def clear_to_num(self, input):
        self.data[self.data != input] = input

    def clear_to_num_greater_than(self, number, number_limit):
        self.data[self.data >= number_limit + 1e-5] = number

    def clear_to_num_less_than(self, number, number_limit):
        self.data[self.data < number_limit - 1e-5] = number


class StationDataArray():
    """站点 id/lon/lat/data 平行数组，供 Cressman 与散点频率匹配使用。"""

    def __init__(self, id_list, lon_list, lat_list, data_list):
        self._id = id_list
        self._lons = lon_list
        self._lats = lat_list
        self._data = data_list

    @property
    def data(self):
        return self._data

    @property
    def lon(self):
        return self._lons

    @property
    def lat(self):
        return self._lats

    @property
    def id(self):
        return self._id

    def clear_to_num(self, num):
        self.data[self.data != num] = num

    def clear_to_num_less_than(self, number, number_limit):
        self.data[self.data < number_limit] = number

    def multi_value(self, apha):
        self._data = self.data * apha


class StationDataDataFrame():

    def __init__(self, filename, station=None, time=None, dtime=None, level=None,
                 show=False):
        self.filename = filename
        self.station = station
        self.time = time
        self.dtime = dtime
        self.level = level
        self.show = show
        self.read_stadata_from_micaps3()

    def read_stadata_from_micaps3(self):
        sta = meb.read_stadata_from_micaps3(self.filename, station=self.station, time=self.time, dtime=self.dtime,
                                            level=self.level, show=self.show)
        self.sta = sta

    def sele_by_para(self, **kwargs):
        sta = self.sta
        sta = meb.sele_by_para(sta,
                               lon=kwargs['lon'],
                               lat=kwargs['lat'])
        self.sta = sta

    def clear_to_num(self, num):
        data = self.sta[data0_str].to_numpy()
        data[data != num] = num
        self.sta[data0_str] = data

    def clear_to_num_less_than(self, number, number_limit):
        data = self.sta[data0_str].to_numpy()
        data[data < number_limit] = number
        self.sta[data0_str] = data

    def multi_value(self, apha):
        data = self.sta[data0_str].to_numpy()
        data = data * apha
        self.sta[data0_str] = data


def write_val_to_micaps4(str_file_path, str_header, array, _yn, _xn, str_fortmat=None):
    try:
        output_dir = os.path.dirname(str_file_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(str_file_path, 'w+', encoding='gb2312') as output_sw:
            output_sw.write(str_header + '\n')
            for j in range(_yn):
                for i in range(_xn):
                    if not str_fortmat:
                        output_str = "{0:8.2f}  ".format(array[i][j])
                        output_sw.write(output_str)
                    else:
                        output_str = f'{array[j][i]:{str_fortmat}} '
                        output_sw.write(output_str)
                output_sw.write('\n')

    except Exception as ex:
        raise ex


def write_float_val_to_bin(str_file_path, array, _yn, _xn):
    try:
        output_dir = os.path.dirname(str_file_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(str_file_path, "wb+") as output_bw:
            for j in range(_yn):
                for i in range(_xn):
                    value = array[i][j]
                    output_bw.write(struct.pack('f', float(value)))

    except Exception as ex:
        raise ex


def write_to_micaps3(str_file_path, str_header, sta):
    id_list = sta['id'].to_numpy()
    lon_list = sta['lon'].to_numpy()
    lat_list = sta['lat'].to_numpy()
    data_list = sta[data0_str].to_numpy()
    try:
        if not os.path.exists(os.path.dirname(str_file_path)):
            os.makedirs(os.path.dirname(str_file_path))
        with open(str_file_path, 'w+', encoding='gb2312') as sw_output:
            sw_output.write(str_header + '\n')
            sw_output.write("  1    {:8d}\n".format(len(id_list)))
            for n in range(len(id_list)):
                sw_output.write("{:8}".format(id_list[n]))
                sw_output.write("{:2}".format(" "))
                sw_output.write("{:8.2f}".format(lon_list[n]))
                sw_output.write("{:2}".format(" "))
                sw_output.write("{:8.2f}".format(lat_list[n]))
                sw_output.write("{:2}".format(" "))
                sw_output.write("{:8.2f}".format(0.0))
                sw_output.write("{:2}".format(" "))
                sw_output.write("{:8.2f}\n".format(data_list[n]))
        del id_list, lon_list, lat_list, data_list
    except Exception as ex:
        raise ex


def get_log(logfile):
    """
    日志，返回logger对象
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(logfile, mode='a', encoding='utf8')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(levelname)s] %(asctime)s  %(message)s"
        "\n-------------------------------------")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger


def get_ts(predict, fact, level, threshold=0.0):
    """
    计算ts评分
    predict：预测数据
    fact：实况数据
    level：降水分级
    threshold：阈值，判断hit + miss + over>=threshold
    """
    if isinstance(predict,list) and isinstance(fact,list):
        hit = 0.0
        miss = 0.0
        over = 0.0
        for i in range(len(predict)):
            i_hfmc_array = mem.hfmc(
                fact[i],
                predict[i],
                grade_list=[level])

            hit = i_hfmc_array[0][0] + hit
            miss = i_hfmc_array[0][1] + miss
            over = i_hfmc_array[0][2] + over
    else:
        i_hfmc_array = mem.hfmc(
            fact,
            predict,
            grade_list=[level])
        hit = i_hfmc_array[0][0]
        miss = i_hfmc_array[0][1]
        over = i_hfmc_array[0][2]

    if threshold != 0.0:
        if hit + miss + over >= threshold:
            ts = hit / (hit + miss + over)
        else:
            ts = 0.0
    else:
        if hit + miss + over != 0:
            ts = hit / (hit + miss + over)
        else:
            ts = 0.0

    return ts


def __split_list_nlist(list0, n):
    ## list0等分为n组
    if len(list0)%n == 0:
        cnt = len(list0)//n
    else:
        cnt = len(list0)//n+1
    for i in range(0,n):
        yield list0[i*cnt : (i+1)*cnt]

def multi_pool_cal(operation, input, pro_count):
    """
    不带返回值的并行同步处理
    ## operation为待并行函数
    ## input为某参数并行列表(list)， pro_count为进程数
    ## 根据pro_count自动将input切分为等长的n份，作为并行参数
    """
    processes_pool = Pool(pro_count)
    input_mpi = list(__split_list_nlist(input, pro_count))
    # 开始并行
    processes_pool.map(operation, input_mpi)
    return None
