# -*- coding: UTF-8 -*-
# @Software : python
import datetime
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
import multiprocessing as mp
from multiprocessing import Pool
# from nimm import PostProcessingPlugin

from utils.util_context import RunContext

data0_str = 'data0'


def copy_data(data):
    new_data = deepcopy(data)
    return new_data


class MetevaFrequencyMatch():
    @staticmethod
    def get_model_level(model_data, fact_data, fact_level, fact_level_limit=None):
        ft_dy_n = len(fact_data)
        md_dy_n = len(model_data)

        lt_ft = []
        lt_md = []
        if isinstance(model_data[0], pd.DataFrame):
            for i in range(ft_dy_n):
                fact_data_array = fact_data[i][data0_str].to_numpy()

                for j in range(len(fact_data[i])):
                    data1 = fact_data_array[j]

                    lt_ft.append(data1 + random.random() / 1000)
                    # lt_ft.append(data1 + 0.885314533614836 / 1000)
                fact_data[i][data0_str] = fact_data_array

            for k in range(md_dy_n):
                model_data_array = model_data[k][data0_str].to_numpy()
                for l in range(len(model_data[k])):
                    data2 = model_data_array[l]
                    lt_md.append(data2 + random.random() / 1000)
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

        ft_dy_n = len(fact_data)
        md_dy_n = len(model_data)

        lt_ft = []
        lt_md = []

        if isinstance(model_data[0], StationDataArray):

            for i in range(ft_dy_n):
                for j in range(len(fact_data[i].id)):
                    lt_ft.append(fact_data[i].data[j] + random.random() / 1000)
                    # lt_ft.append(fact_data[i].data[j] + 0.885314533614836 / 1000)

            for k in range(md_dy_n):
                for l in range(len(model_data[k].id)):
                    lt_md.append(model_data[k].data[l] + random.random() / 1000)
                    # lt_md.append(model_data[k].data[l] + 0.885314533614836 / 1000)

        elif isinstance(model_data[0], pd.DataFrame):

            for i in range(ft_dy_n):
                for j in range(len(fact_data[i])):
                    lt_ft.append(fact_data[i][data0_str].to_numpy()[j] + random.random() / 1000)
                    # lt_ft.append(fact_data[i][data0_str].to_numpy()[j] + 0.885314533614836 / 1000)

            for k in range(md_dy_n):
                for l in range(len(model_data[k])):
                    lt_md.append(model_data[k][data0_str].to_numpy()[l] + random.random() / 1000)
                    # lt_md.append(model_data[k][data0_str].to_numpy()[l] + 0.885314533614836 / 1000)

        elif isinstance(model_data[0], float):
            for i in range(ft_dy_n):
                # lt_ft.append(fact_data[i] + 0.885314533614836 / 1000)
                lt_ft.append(fact_data[i] + random.random() / 1000)

            for j in range(md_dy_n):
                # lt_md.append(model_data[j] + 0.885314533614836 / 1000)
                lt_md.append(model_data[j] + random.random() / 1000)

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
        if isinstance(model_data, StationDataArray):
            model_data = MetevaFrequencyMatch.correct_model_data_scatter(model_data, fact_level, model_level)
        if isinstance(model_data, pd.DataFrame):
            model_data = MetevaFrequencyMatch.correct_model_data_scatter_df(model_data, fact_level, model_level)
        elif isinstance(model_data, GridData):
            model_data = MetevaFrequencyMatch.correct_model_data_grid(model_data, fact_level, model_level)
        elif isinstance(model_data, NcData):
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
        gd_output_data_tmp = gd_background_data
        for n in range(len(distance_limits)):
            gd_output_data_tmp = MetevaSpatialAnalisis.cressman_one_step_interpolation_for_rain(sd_input_data,
                                                                                                gd_output_data_tmp,
                                                                                                distance_limits[n],
                                                                                                num_limit,
                                                                                                smooth, power_param,
                                                                                                rain_limit)
        return gd_output_data_tmp


# 由双线性插值到散点值
def bilinear_interpolation_from_grid_data(sd_reference, input_data, db_undef=0.0):
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


class NcData():

    def __init__(self, file):
        self.file = file
        self.read_griddata_from_nc()

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

    def read_griddata_from_nc(self):
        ds = meb.read_griddata_from_nc(self.file)
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

    def __init__(self, id_list, lon_list, lat_list, data_list):
        if isinstance(id_list, pd.Series):
            id_list = id_list.values
        if isinstance(lon_list, pd.Series):
            lon_list = lon_list.values
        if isinstance(lat_list, pd.Series):
            lat_list = lat_list.values
        if isinstance(data_list, pd.Series):
            data_list = data_list.values
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


def get_log(logfile, logger_name="mait_24h"):
    """
    创建独立命名 logger，避免多进程共享根 logger 与重复挂载 handler。
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    fh = logging.FileHandler(logfile, mode='a', encoding='utf8')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "[%(levelname)s] %(asctime)s  %(message)s"
        "\n-------------------------------------")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


def init_run_log(log_file_template, time_input=None):
    """创建独立 logger；子进程按 time_input+pid 分文件，避免多进程写冲突。"""
    log_path = meb.get_path(log_file_template, datetime.datetime.now(), 0)
    suffix = []
    if time_input:
        suffix.append(str(time_input))
    if mp.current_process().name != "MainProcess":
        suffix.append(str(os.getpid()))
    if suffix:
        base, ext = os.path.splitext(log_path)
        log_path = "%s_%s%s" % (base, "_".join(suffix), ext)
    log_dir = os.path.dirname(log_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logger_name = "mait_24h" + ("." + ".".join(suffix) if suffix else "")
    return get_log(log_path, logger_name=logger_name)


def get_ts(predict, fact, level, threshold=0.0):
    """
    计算ts评分
    predict：预测数据
    fact：实况数据
    level：降水分级
    threshold：阈值，判断hit + miss + over>=threshold
    """
    if isinstance(predict, list) and isinstance(fact, list):
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
    if len(list0) % n == 0:
        cnt = len(list0) // n
    else:
        cnt = len(list0) // n + 1
    for i in range(0, n):
        yield list0[i * cnt: (i + 1) * cnt]


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


def read_grid_mask(mask_file, grid_base):
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    d_lon = grid_base.dlon
    d_lat = grid_base.dlat

    # 中国范围里面是1，外面是-1
    gd_mask_val, gd_mask_xn, gd_mask_yn = read_float_val_from_bin(mask_file, lon_start, lon_end,
                                                                  lat_start, lat_end, d_lon,
                                                                  d_lat)
    return gd_mask_val, gd_mask_xn, gd_mask_yn


def read_grid_mask_nc(mask_file):
    _grid = meb.read_griddata_from_nc(mask_file)
    # print(_grid)
    data = _grid.data
    shape = data.shape
    _data = data[0, 0, 0, 0, :]
    # _data = np.flipud(_data)
    _data = _data.transpose()
    gd_mask_val, gd_mask_xn, gd_mask_yn = _data, shape[-1], shape[-2]
    return gd_mask_val, gd_mask_xn, gd_mask_yn

    # _data = np.flipud(_data)
    # # _data = _data.transpose()
    # gd_mask_val, gd_mask_xn, gd_mask_yn = _data, shape[-2], shape[-1]
    # return gd_mask_val, gd_mask_xn, gd_mask_yn


def save_grid_mask_png(gd_mask_val, png_name):
    from PIL import Image
    height, width = gd_mask_val.shape
    rgb_array = np.zeros((height, width, 3), dtype=np.uint8)

    # 负值：黑色 (0,0,0)，正值：红色 (255,0,0)
    mask_positive = gd_mask_val > 0
    rgb_array[mask_positive, 0] = 255  # 红色通道
    # 其他通道保持0（黑色）

    # 保存为PNG
    img = Image.fromarray(rgb_array, 'RGB')
    img.save(png_name)
    # img.show()

    return None


def _prepare(time_input, sd_sta_info_file):
    """解析起报时间并读取站点表（不写日志）。"""
    if time_input is None:
        dt_now = datetime.datetime.now()
    else:
        dt_now = datetime.datetime.strptime(time_input, "%Y%m%d%H%M")

    sd_sta_info = meb.read_stadata_from_micaps3(sd_sta_info_file)
    sd_sta_info.iloc[:, -1] = 0.0
    return dt_now, sd_sta_info


def _analysis_para_ini(para_filepath):
    """解析 para ini（不写日志）；失败返回 None。"""
    if not os.path.exists(para_filepath):
        return
    with open(para_filepath, 'r', encoding='GBK') as para_sr:
        try:
            str_tmp = para_sr.readline()
            str_array_tmp = str_tmp.split("=")
            model_num = int(str_array_tmp[1])
            model_name = list()
            model_path = list()
            for n in range(model_num):
                str_tmp = para_sr.readline()
                str_array_tmp = str_tmp.split("=")
                model_name.append(str_array_tmp[0].strip())
                model_path.append(str_array_tmp[1].strip())
            str_tmp = para_sr.readline()
            str_array_tmp = str_tmp.split("=")
            fact_path = str_array_tmp[1].strip()
            str_tmp = para_sr.readline()
            str_array_tmp = str_tmp.split("=")
            output_sample_path = str_array_tmp[1].strip()
            return model_name, model_path, fact_path, output_sample_path
        except Exception:
            return


def _data_write_to_micaps3(sd_output, grid_base, ctx: RunContext):
    """
    输出micaps3
    :return:
    """
    predict_type = ctx.grid.predict_type
    output_sample_path = ctx.paths.output_sample_path

    sta_header = meb.get_path(
        f"diamond 3 YYYY年MM月DD日HH时VVV时效{predict_type:03d}小时累积降水 00 01 04 08  -1 0 1 0 0".replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    output_sta_path = meb.get_path(
        output_sample_path.replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    sd_output[data0_str] = sd_output[data0_str] * 1.0
    os.makedirs(os.path.dirname(output_sta_path), exist_ok=True)
    meb.set_stadata_coords(sd_output,
                           time=grid_base.gtime[0], dtime=grid_base.dtimes[0])
    meb.write_stadata_to_micaps3(sd_output, save_path=output_sta_path + '.m3',
                                 effectiveNum=2)
    return output_sta_path + '.m3'


# def write_grid_to_micaps4(gd_final_output, output_sample_path, predict_type, clip_coords, grid_base, is_interp):
def write_grid_to_micaps4(gd_final_output, grid_base, ctx: RunContext):

    output_sample_path = ctx.paths.output_sample_path
    predict_type = ctx.grid.predict_type
    clip_coords = ctx.grid.clip_coords

    grid_no_interp = meb.grid_data(grid_base, gd_final_output.data.T)
    grid = grid_no_interp
    # 插值
    # if is_interp == True:
    if clip_coords:
        if len(clip_coords) == 6:
            lon_start_clip = clip_coords[0]
            lon_end_clip = clip_coords[1]
            lat_start_clip = clip_coords[2]
            lat_end_clip = clip_coords[3]
            dlon_clip = clip_coords[4]
            dlat_clip = clip_coords[5]
            grid_clip = meb.grid([lon_start_clip, lon_end_clip, dlon_clip],
                                 [lat_start_clip, lat_end_clip, dlat_clip])
            grid = meb.interp_gg_linear(grid_no_interp, grid_clip)

    output_grid_path = meb.get_path(
        output_sample_path.replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    os.makedirs(os.path.dirname(output_grid_path), exist_ok=True)

    micaps4_file2 = output_grid_path + ".m4"

    grid_header2 = meb.get_path(
        f"YYYYMMDDHH_VVV时效{predict_type:03d}小时降水预报场".replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])

    meb.write_griddata_to_micaps4(grid, micaps4_file2, creat_dir=True, effectiveNum=2, title=grid_header2, inte=5,
                                  vmin=0, vmax=200)
    meb.write_griddata_to_nc(grid, output_grid_path + ".nc", creat_dir=True, effectiveNum=2)
    return None


def get_his_beta_file_path(beta_path, grid_base, split_lat, split_lon):
    """
    获取历史的beta文件路径
    :param app_dir: 程序目录
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: beta文件列表和文件是否存在的标识list，list    文件存在[[[beta_file]]],[[[1]]]，文件不存在文件存在[[['0']]],[[[0]]]
    """
    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    ibeta_file_path_list = []
    iflag_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]

    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_ibeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()
        ii_iflag_list = np.full(shape=(yyn, xxn), fill_value=0, dtype=int).tolist()

        for j in range(yyn):
            for i in range(xxn):

                for n in range(1, 10):
                    dti_beta = dto_beta - datetime.timedelta(days=n)  # 计算输入参数文件的日期
                    ibeta_file_path = meb.get_path(os.path.join(beta_path, '%02d_%02d_TTT.info' % (i, j)),
                                                   dti_beta,
                                                   predict_valid)  # 生成当前参数文件路径
                    if os.path.exists(ibeta_file_path):
                        ii_ibeta_file_path_list[j][i] = ibeta_file_path
                        ii_iflag_list[j][i] = 1
                        # iflag = 1
                        break
        ibeta_file_path_list.append(ii_ibeta_file_path_list)
        iflag_list.append(ii_iflag_list)
    return ibeta_file_path_list, iflag_list


def get_his_beta_file_path_npy(grid_base, ctx: RunContext):
    """
    获取历史的beta文件路径
    :param app_dir: 程序目录
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: beta文件列表和文件是否存在的标识list，list    文件存在[[[beta_file]]],[[[1]]]，文件不存在文件存在[[['0']]],[[[0]]]
    """

    beta_path = ctx.paths.beta_path_template
    split_lat = ctx.grid.split_lat
    split_lon = ctx.grid.split_lon

    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    ibeta_file_path_list = []
    iflag_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]

    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_ibeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()
        ii_iflag_list = np.full(shape=(yyn, xxn), fill_value=0, dtype=int).tolist()

        for j in range(yyn):
            for i in range(xxn):
                for n in range(1, 10):
                    dti_beta = dto_beta - datetime.timedelta(days=n)  # 计算输入参数文件的日期
                    ibeta_file_path = meb.get_path(os.path.join(beta_path, '%02d_%02d_TTT.npy' % (i, j)),
                                                   dti_beta,
                                                   predict_valid)  # 生成当前参数文件路径
                    if os.path.exists(ibeta_file_path):
                        ii_ibeta_file_path_list[j][i] = ibeta_file_path
                        ii_iflag_list[j][i] = 1
                        # iflag = 1
                        break
        ibeta_file_path_list.append(ii_ibeta_file_path_list)
        iflag_list.append(ii_iflag_list)
    return ibeta_file_path_list, iflag_list


def get_now_beta_file_path(beta_path, grid_base, split_lat, split_lon):
    """
    获取当前的beta文件路径
    :param beta_path: beta文件路径，默认为None
    :param app_dir: 程序目录
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: list，[[[beta_file]]]
    """
    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    obeta_file_path_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_obeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            for i in range(xxn):
                obeta_file_path = meb.get_path(os.path.join(beta_path, '%02d_%02d_TTT.info' % (i, j)),
                                               dto_beta,
                                               predict_valid)  # 生成当前参数文件路径
                ii_obeta_file_path_list[j][i] = obeta_file_path
        obeta_file_path_list.append(ii_obeta_file_path_list)

    return obeta_file_path_list


def get_now_beta_file_path_npy(grid_base, ctx: RunContext):
    """
    获取当前的beta文件路径
    :param beta_path: beta文件路径，默认为None
    :param app_dir: 程序目录
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: list，[[[beta_file]]]
    """

    beta_path = ctx.paths.beta_path_template
    split_lat = ctx.grid.split_lat
    split_lon = ctx.grid.split_lon

    dto_beta = grid_base.gtime[0]  # 输出参数文件日期
    predict_valid = grid_base.dtimes[0]

    obeta_file_path_list = []
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_obeta_file_path_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            for i in range(xxn):
                obeta_file_path = meb.get_path(os.path.join(beta_path, '%02d_%02d_TTT.npy' % (i, j)),
                                               dto_beta,
                                               predict_valid)  # 生成当前参数文件路径
                ii_obeta_file_path_list[j][i] = obeta_file_path
        obeta_file_path_list.append(ii_obeta_file_path_list)

    return obeta_file_path_list


def read_his_beta(ibeta_file_path_list, iflag_list, model_name, grid_base, split_lat, split_lon):
    """
    读取历史的beta文件
    :param ibeta_file_path_list: 历史beta文件list
    :param iflag_list: 历史beta文件是否存在的标识的list
    :param model_num: 模式个数
    :param model_name: 模式名称list
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: 历史评分，beta文件是否存在的标识，list，list
    """
    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]
    score_before_list = []
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_score_before_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            for i in range(xxn):
                score_before = [0.0] * len(model_name)  # 得分 score-before，之前得分

                ibeta_file_path = ibeta_file_path_list[i_num][j][i]
                iflag = iflag_list[i_num][j][i]
                if iflag == 1:
                    # 读取
                    with open(ibeta_file_path, 'r') as beta_sr:
                        while True:
                            str_tmp = beta_sr.readline()
                            if str_tmp:
                                str_tmp_array = str_tmp.split('=')
                                for n in range(len(model_name)):  # 不存在的前期的模式信息就为0.0
                                    if str_tmp_array[0].strip() == model_name[n]:
                                        score_before[n] = float(str_tmp_array[1].strip())
                            else:
                                break
                ii_score_before_list[j][i] = score_before
        score_before_list.append(ii_score_before_list)

    return score_before_list, iflag_list


def read_his_beta_npy(ibeta_file_path_list, iflag_list, grid_base, ctx: RunContext):
    """
    读取历史的beta文件
    :param ibeta_file_path_list: 历史beta文件list
    :param iflag_list: 历史beta文件是否存在的标识的list
    :param model_num: 模式个数
    :param model_names: 模式名称list
    :param grid_base: 格点数据实况坐标，时间时效等
    :return: 历史评分，beta文件是否存在的标识，list，list
    """

    model_names = ctx.models.model_name
    split_lat = ctx.grid.split_lat
    split_lon = ctx.grid.split_lon


    lon_start = grid_base.slon
    lon_end = grid_base.elon
    lat_start = grid_base.slat
    lat_end = grid_base.elat
    # lon_interval = [lon_end - lon_start]
    # lat_interval = [lat_end - lat_start]
    lon_interval = [(lon_end - lon_start) / split_lon]
    lat_interval = [(lat_end - lat_start) / split_lat]
    score_before_list = []
    for i_num in range(len(lon_interval)):
        xxn = int((lon_end - lon_start) / lon_interval[i_num])
        yyn = int((lat_end - lat_start) / lat_interval[i_num])

        ii_score_before_list = np.full(shape=(yyn, xxn), fill_value='0', dtype=str).tolist()

        for j in range(yyn):
            for i in range(xxn):
                score_before = [0.0] * len(model_names)  # 得分 score-before，之前得分

                ibeta_file_path = ibeta_file_path_list[i_num][j][i]
                iflag = iflag_list[i_num][j][i]
                if iflag == 1:
                    # 读取
                    loaded_data = np.load(ibeta_file_path)
                    if len(loaded_data) == 0:
                        break
                    else:
                        for n, model_name in enumerate(model_names):
                            if loaded_data[n]['model_name'] == model_name:
                                score_before[n] = float(loaded_data[n]['value'])

                    # with open(ibeta_file_path, 'r') as beta_sr:
                    #     while True:
                    #         str_tmp = beta_sr.readline()
                    #         if str_tmp:
                    #             str_tmp_array = str_tmp.split('=')
                    #             for n in range(len(model_name)):  # 不存在的前期的模式信息就为0.0
                    #                 if str_tmp_array[0].strip() == model_name[n]:
                    #                     score_before[n] = float(str_tmp_array[1].strip())
                    #         else:
                    #             break
                ii_score_before_list[j][i] = score_before
        score_before_list.append(ii_score_before_list)
    return score_before_list, iflag_list


def write_beta(obeta_file_path, model_name, score_last):
    """
    权重系数写入到beta文件中
    :param obeta_file_path: beta文件
    :param model_num: 模式个数
    :param model_name: 模式名称list
    :param score_last: 最终评分
    :return:
    """
    os.makedirs(os.path.dirname(obeta_file_path), exist_ok=True)
    with open(obeta_file_path, 'w+') as obeta_sr:
        for n in range(len(model_name)):
            obeta_sr.write(model_name[n] + "=" + str(score_last[n]) + "\n")
    return None


def write_beta_npy(obeta_file_path, model_name, score_last):
    """
    权重系数写入到beta文件中
    :param obeta_file_path: beta文件
    :param model_num: 模式个数
    :param model_name: 模式名称list
    :param score_last: 最终评分
    :return:
    """
    model_score_list = []
    for n, model_name in enumerate(model_name):
        model_score_list.append((model_name, score_last[n]))

    os.makedirs(os.path.dirname(obeta_file_path), exist_ok=True)
    data = np.array(model_score_list, dtype=[('model_name', 'U20'), ('value', 'f8')])
    # 保存为 .npy 文件
    np.save(obeta_file_path, data)

    return None


# class MultiPoolCal(PostProcessingPlugin):
class MultiPoolCal():
    """
    多进程由函数写成类，里面需要包含process函数，参数为dtimes和pro_count以及调用的函数或类
    """

    def __init__(self, func=None, dtimes: list = None, pro_count: int = 3):
        self.func = func
        self.dtimes = dtimes
        self.pro_count = pro_count

    def process(self):
        multi_pool_cal(self.func, self.dtimes, self.pro_count)
        return None


def write_grid_to_micaps4_threshold(grid_data, output_sample_path, predict_type, clip_coords, grid_base):
    lon_start_clip = clip_coords[0]
    lon_end_clip = clip_coords[1]
    lat_start_clip = clip_coords[2]
    lat_end_clip = clip_coords[3]
    dlon_clip = clip_coords[4]
    dlat_clip = clip_coords[5]
    grid_clip = meb.grid(
        [lon_start_clip, lon_end_clip, dlon_clip],
        [lat_start_clip, lat_end_clip, dlat_clip],
        gtime=grid_base.gtime, dtime_list=grid_base.dtimes)
    grid = meb.grid_data(grid_clip, grid_data)

    output_grid_path = meb.get_path(
        output_sample_path.replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])
    os.makedirs(os.path.dirname(output_grid_path), exist_ok=True)

    micaps4_file2 = output_grid_path + ".m4"

    grid_header2 = meb.get_path(
        f"YYYYMMDDHH_VVV时效{predict_type:03d}小时降水预报场".replace('VVV', 'TTT'),
        grid_base.gtime[0],
        grid_base.dtimes[0])

    meb.write_griddata_to_micaps4(grid, micaps4_file2, creat_dir=True, effectiveNum=2, title=grid_header2, inte=5,
                                  vmin=0, vmax=200)
    meb.write_griddata_to_nc(grid, output_grid_path + ".nc", creat_dir=True, effectiveNum=2)
    return None


