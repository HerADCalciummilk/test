# -- coding: utf-8 --
# @Time : 2025/1/20 14:25
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : cal_frequencyMatch.py
# @Software: PyCharm

import numpy as np
import pandas as pd
import xarray as xr

class FrequencyMatch:

    def __init__(self, model_data, fact_data, fact_level, fact_level_limit=None):

        self.model_data = model_data
        self.fact_data = fact_data
        self.fact_level = fact_level
        self.fact_level_limit = fact_level_limit

    def get_used_model_level_grd(self):
        fact_level = np.array(self.fact_level)
        ft_dy_n = len(self.fact_data)
        md_dy_n = len(self.model_data)

        doubleList1 = []
        doubleList2 = []

        if isinstance(self.model_data[0], pd.DataFrame):
            pd_ft = pd.concat(self.fact_data, ignore_index=True).data0
            pd_md = pd.concat(self.model_data, ignore_index=True).data0
            # doubleList1 = (pd_ft + np.random.rand(len(pd_ft)) / 1000).to_numpy()
            # doubleList2 = (pd_md + np.random.rand(len(pd_md)) / 1000).to_numpy()
            doubleList1 = pd_ft.to_numpy()
            doubleList2 = pd_md.to_numpy()

        elif isinstance(self.model_data[0], xr.DataArray):
            for i in range(ft_dy_n):
                array = self.fact_data[i].data.squeeze()
                # doubleList1.append(array + np.random.rand(*array.shape) / 1000)
                doubleList1.append(array)
            for l in range(md_dy_n):
                array = self.model_data[l].data.squeeze()
                # doubleList2.append(array + np.random.rand(*array.shape) / 1000)
                doubleList2.append(array)

        array1 = np.sort(np.array(doubleList1).flatten())
        array2 = np.sort(np.array(doubleList2).flatten())

        level_n = len(fact_level)
        model_level = np.zeros((2, level_n))

        if not self.fact_level_limit:
            for i in range(level_n):
                if (fact_level[i] >= array1[-1]) or (fact_level[i] < array1[0]):
                    model_level[0][i] = 0
                    model_level[1][i] = fact_level[i]
                else:
                    for j in range(len(array1)-1):
                        if (fact_level[i] >= array1[j]) and (fact_level[i] < array1[j + 1]):
                            k = int((j + 1) / len(array1) * len(array2)) - 1
                            if (k < 0) or (k >= len(array2) - 1):
                                model_level[0][i] = 0
                                model_level[1][i] = fact_level[i]
                            else:
                                model_level[0][i] = 1
                                model_level[1][i] = array2[k] + (array2[k + 1] - array2[k]) * \
                                                    (fact_level[i] - array1[j]) / \
                                                    (array1[j + 1] - array1[j])

        used_indices = np.arange(level_n)
        condition = abs(model_level[0, used_indices] - 0.0) > 1e-5
        used_list = model_level[1, used_indices[condition]]
        used_fact_list = fact_level[used_indices[condition]]

        return np.array([used_list, used_fact_list])

    def get_used_model_level_sta(self):
        fact_level = np.array(self.fact_level)

        pd_ft = pd.concat(self.fact_data, ignore_index=True).data0
        pd_md = pd.concat(self.model_data, ignore_index=True).data0
        doubleList1 = (pd_ft + np.random.rand(len(pd_ft)) / 1000).to_numpy()
        doubleList2 = (pd_md + np.random.rand(len(pd_md)) / 1000).to_numpy()
        # doubleList1 = pd_ft.to_numpy()
        # doubleList2 = pd_md.to_numpy()

        array1 = np.sort(np.array(doubleList1).flatten())
        array2 = np.sort(np.array(doubleList2).flatten())

        level_n = len(fact_level)
        model_level = np.zeros((2, level_n))

        for index5 in range(len(fact_level)):
            if self.fact_level_limit < 0.5 * (len(array1) - 1):
                if (fact_level[index5] >= array1[len(array1) - 1 - self.fact_level_limit]) or \
                        (fact_level[index5] < array1[self.fact_level_limit]):
                    model_level[0][index5] = 0.0
                    model_level[1][index5] = fact_level[index5]
                else:
                    for index6 in range(self.fact_level_limit, len(array1) - 1 - self.fact_level_limit, 1):
                        if (fact_level[index5] > array1[index6]) and (fact_level[index5] <= array1[index6 + 1]):
                            index7 = int((index6 + 1.0) / float(len(array1)) * float(len(array2))) - 1
                            if (index7 < 0) or (index7 >= len(array2) - 1):
                                model_level[0][index5] = 0.0
                                model_level[1][index5] = fact_level[index5]
                            else:
                                model_level[0][index5] = 1.0
                                model_level[1][index5] = array2[index7] + (array2[index7 + 1] - array2[index7]) * (
                                        fact_level[index5] - array1[index6]) / (array1[index6 + 1] - array1[index6])
            else:
                model_level[0][index5] = 0.0
                model_level[1][index5] = fact_level[index5]

        double_list3 = list()
        double_list4 = list()

        for index in range(level_n):
            if model_level[0][index] != 0.0:
                double_list3.append(model_level[1][index])
                double_list4.append(fact_level[index])

        return np.array([double_list3, double_list4])

    def get_used_model_level_and_extend(self, label):
        if label == 'grd':
            used_model_level = self.get_used_model_level_grd()
        else:
            used_model_level = self.get_used_model_level_sta()

        if len(used_model_level[0]) == 0 or len(used_model_level[0]) >= len(self.fact_level):
            return used_model_level

        model_level_and_extend = np.zeros((2, len(used_model_level[0]) + 1))
        for index in range(len(used_model_level[0])):
            model_level_and_extend[0][index] = used_model_level[0][index]
            model_level_and_extend[1][index] = used_model_level[1][index]

        for index in range(len(self.fact_level)):
            if self.fact_level[index] > used_model_level[1][-1]:
                model_level_and_extend[0][-1] = max(
                    model_level_and_extend[0][-2] * 2.0, self.fact_level[index])
                model_level_and_extend[1][-1] = self.fact_level[index]
                break
        return model_level_and_extend

    @staticmethod
    def correct_model_grid(model_grd: xr.DataArray, tp_level):
        fact_level, model_level = tp_level[1], tp_level[0]
        grid_data = model_grd.copy()
        grd_array = grid_data.data.squeeze()
        num = len(fact_level)

        if num == 0:
            return grid_data

        result_array = grd_array.copy()
        mask = grd_array < model_level[0]
        result_array[mask] = np.where(model_level[0] != 0.0, grd_array[mask] * fact_level[0] / model_level[0], 0.0)

        for index3 in range(num - 1):
            mask = (model_level[index3] <= grd_array) & (grd_array < model_level[index3 + 1])
            if np.sum(mask) == 0:
                continue
            result_array[mask] = fact_level[index3] + (fact_level[index3 + 1] - fact_level[index3]) \
                                 * (grd_array[mask] - model_level[index3]) / \
                                 (model_level[index3 + 1] - model_level[index3])

        mask = grd_array >= model_level[-1]
        result_array[mask] = np.where(model_level[-1] != 0.0, grd_array[mask] * fact_level[-1] / model_level[-1], 0.0)

        grid_data.data = [[[[result_array]]]]
        return grid_data