# -*- coding: utf-8 -*-
"""分位频率匹配：排序参考/模式样本，按实况级插出模式阈值并分段线性订正。"""
import math
import numpy as np
from utils.types import GridData, ScatterData


class FrequencyMatch:
    """由参考场与模式场建立级映射，再分段线性订正站点 / 格点 / 数组。"""

    @staticmethod
    def get_model_level(model_data, fact_data, fact_level, fact_level_limit=None):
        """对样本排序（含 \(U(0,10^{-3})\) 扰动），按 ``fact_level`` 分位插出模式阈值。"""
        if isinstance(model_data[0], ScatterData):
            return FrequencyMatch._get_model_level_scatter(model_data, fact_data, fact_level, fact_level_limit)
        elif isinstance(model_data[0], GridData):
            return FrequencyMatch._get_model_level_grid(model_data, fact_data, fact_level, fact_level_limit)
        else:
            return FrequencyMatch._get_model_level_array(model_data, fact_data, fact_level, fact_level_limit)

    @staticmethod
    def _get_model_level_scatter(model_data, fact_data, fact_level, fact_level_limit=None):
        lst_fact = []
        lst_model = []
        for sd in fact_data:
            for pd in sd.sta_data:
                lst_fact.append(pd.val)
        for sd in model_data:
            for pd in sd.sta_data:
                lst_model.append(pd.val)
        # Add random perturbation with numpy (single call, much faster than per-value)
        lst_fact_arr = np.array(lst_fact, dtype=np.float64)
        lst_model_arr = np.array(lst_model, dtype=np.float64)
        lst_fact_arr += np.random.random(len(lst_fact_arr)) / 1000.0  # 原算法扰动，避免同分位黏连
        lst_model_arr += np.random.random(len(lst_model_arr)) / 1000.0
        arr = np.sort(lst_fact_arr)
        arr2 = np.sort(lst_model_arr)
        num3 = len(fact_level)
        arr3 = [[0.0] * num3, [0.0] * num3]
        for m in range(len(fact_level)):
            if fact_level_limit is not None:
                if fact_level_limit < 0.5 * (len(arr) - 1):
                    if fact_level[m] >= arr[len(arr) - 1 - fact_level_limit] or fact_level[m] < arr[fact_level_limit]:
                        arr3[0][m] = 0.0
                        arr3[1][m] = fact_level[m]
                        continue
                    for n in range(fact_level_limit, len(arr) - 1 - fact_level_limit):
                        if arr[n] < fact_level[m] <= arr[n + 1]:
                            num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                            if num4 < 0 or num4 >= len(arr2) - 1:
                                arr3[0][m] = 0.0
                                arr3[1][m] = fact_level[m]
                            else:
                                arr3[0][m] = 1.0
                                arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
                else:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
            else:
                if fact_level[m] >= arr[-1] or fact_level[m] < arr[0]:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
                    continue
                for n in range(len(arr) - 1):
                    if arr[n] <= fact_level[m] < arr[n + 1]:
                        num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                        if num4 < 0 or num4 >= len(arr2) - 1:
                            arr3[0][m] = 0.0
                            arr3[1][m] = fact_level[m]
                        else:
                            arr3[0][m] = 1.0
                            arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
        return arr3

    @staticmethod
    def _get_model_level_grid(model_data, fact_data, fact_level, fact_level_limit=None):
        # collect all grid values with random perturbation using numpy
        fact_parts = [gd.val.ravel() for gd in fact_data]
        model_parts = [gd.val.ravel() for gd in model_data]
        if fact_parts:
            fact_concat = np.concatenate(fact_parts)
            fact_concat += np.random.random(len(fact_concat)) / 1000.0
            arr = np.sort(fact_concat)
        else:
            arr = np.array([], dtype=np.float64)
        if model_parts:
            model_concat = np.concatenate(model_parts)
            model_concat += np.random.random(len(model_concat)) / 1000.0
            arr2 = np.sort(model_concat)
        else:
            arr2 = np.array([], dtype=np.float64)
        num3 = len(fact_level)
        arr3 = [[0.0] * num3, [0.0] * num3]
        for m in range(len(fact_level)):
            if fact_level_limit is not None:
                if fact_level_limit < 0.5 * (len(arr) - 1):
                    if fact_level[m] >= arr[len(arr) - 1 - fact_level_limit] or fact_level[m] < arr[fact_level_limit]:
                        arr3[0][m] = 0.0
                        arr3[1][m] = fact_level[m]
                        continue
                    for n in range(fact_level_limit, len(arr) - 1 - fact_level_limit):
                        if arr[n] < fact_level[m] <= arr[n + 1]:
                            num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                            if num4 < 0 or num4 >= len(arr2) - 1:
                                arr3[0][m] = 0.0
                                arr3[1][m] = fact_level[m]
                            else:
                                arr3[0][m] = 1.0
                                arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
                else:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
            else:
                if fact_level[m] >= arr[-1] or fact_level[m] < arr[0]:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
                    continue
                for n in range(len(arr) - 1):
                    if arr[n] <= fact_level[m] < arr[n + 1]:
                        num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                        if num4 < 0 or num4 >= len(arr2) - 1:
                            arr3[0][m] = 0.0
                            arr3[1][m] = fact_level[m]
                        else:
                            arr3[0][m] = 1.0
                            arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
        return arr3

    @staticmethod
    def _get_model_level_array(model_data, fact_data, fact_level, fact_level_limit=None):
        lst_fact = np.array(fact_data, dtype=np.float64)
        lst_model = np.array(model_data, dtype=np.float64)
        lst_fact += np.random.random(len(lst_fact)) / 1000.0
        lst_model += np.random.random(len(lst_model)) / 1000.0
        arr = np.sort(lst_fact)
        arr2 = np.sort(lst_model)
        num3 = len(fact_level)
        arr3 = [[0.0] * num3, [0.0] * num3]
        for m in range(len(fact_level)):
            if fact_level_limit is not None:
                if fact_level_limit < 0.5 * (len(arr) - 1):
                    if fact_level[m] >= arr[len(arr) - 1 - fact_level_limit] or fact_level[m] < arr[fact_level_limit]:
                        arr3[0][m] = 0.0
                        arr3[1][m] = fact_level[m]
                        continue
                    for n in range(fact_level_limit, len(arr) - 1 - fact_level_limit):
                        if arr[n] < fact_level[m] <= arr[n + 1]:
                            num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                            if num4 < 0 or num4 >= len(arr2) - 1:
                                arr3[0][m] = 0.0
                                arr3[1][m] = fact_level[m]
                            else:
                                arr3[0][m] = 1.0
                                arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
                else:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
            else:
                if fact_level[m] >= arr[-1] or fact_level[m] < arr[0]:
                    arr3[0][m] = 0.0
                    arr3[1][m] = fact_level[m]
                    continue
                for n in range(len(arr) - 1):
                    if arr[n] <= fact_level[m] < arr[n + 1]:
                        num4 = int((n + 1.0) / len(arr) * len(arr2)) - 1
                        if num4 < 0 or num4 >= len(arr2) - 1:
                            arr3[0][m] = 0.0
                            arr3[1][m] = fact_level[m]
                        else:
                            arr3[0][m] = 1.0
                            arr3[1][m] = arr2[num4] + (arr2[num4 + 1] - arr2[num4]) * (fact_level[m] - arr[n]) / (arr[n + 1] - arr[n])
        return arr3

    @staticmethod
    def get_used_model_level(model_data, fact_data, fact_level, fact_level_limit=None):
        """同 ``get_model_level``，只返回有效（可映射）的级对。"""
        if fact_level_limit is not None:
            arr3 = FrequencyMatch.get_model_level(model_data, fact_data, fact_level, fact_level_limit)
        else:
            arr3 = FrequencyMatch.get_model_level(model_data, fact_data, fact_level)
        list3 = []
        list4 = []
        for num5 in range(len(fact_level)):
            if arr3[0][num5] != 0.0:
                list3.append(arr3[1][num5])
                list4.append(fact_level[num5])
        return [list3, list4]

    @staticmethod
    def get_used_model_level_and_extend(model_data, fact_data, fact_level, fact_level_limit=None):
        """有效级对不足时，按末级外推一档以覆盖更大实况量级。"""
        if fact_level_limit is not None:
            used_model_level = FrequencyMatch.get_used_model_level(model_data, fact_data, fact_level, fact_level_limit)
        else:
            used_model_level = FrequencyMatch.get_used_model_level(model_data, fact_data, fact_level)
        if len(used_model_level[0]) != 0:
            if len(used_model_level[0]) < len(fact_level):
                arr0 = list(used_model_level[0]) + [0.0]
                arr1 = list(used_model_level[1]) + [0.0]
                for j in range(len(fact_level)):
                    if fact_level[j] > used_model_level[1][-1]:
                        arr0[-1] = max(arr0[-2] * 2.0, fact_level[j])
                        arr1[-1] = fact_level[j]
                        break
                return [arr0, arr1]
            return used_model_level
        return used_model_level

    @staticmethod
    def correct_model_data(model_data, fact_level, model_level):
        """按级对分段线性订正 ``ScatterData`` / ``GridData`` / 数组。"""
        if isinstance(model_data, ScatterData):
            return FrequencyMatch._correct_scatter(model_data, fact_level, model_level)
        elif isinstance(model_data, GridData):
            return FrequencyMatch._correct_grid(model_data, fact_level, model_level)
        else:
            return FrequencyMatch._correct_array(model_data, fact_level, model_level)

    @staticmethod
    def _correct_scatter(model_data, fact_level, model_level):
        sd = model_data.copy_scatter_data()
        num = len(fact_level)
        if num == 0:
            return model_data
        vals = np.array([pd.val for pd in model_data.sta_data], dtype=np.float64)
        ml = np.array(model_level, dtype=np.float64)
        fl = np.array(fact_level, dtype=np.float64)
        result = np.empty_like(vals)

        mask_below = vals < ml[0]
        if ml[0] == 0.0:
            result[mask_below] = 0.0
        else:
            result[mask_below] = vals[mask_below] * (fl[0] / ml[0])

        mask_above = vals >= ml[-1]
        if ml[-1] == 0.0:
            result[mask_above] = 0.0
        else:
            result[mask_above] = vals[mask_above] * (fl[-1] / ml[-1])

        mask_mid = ~mask_below & ~mask_above
        if mask_mid.any():
            for k in range(num - 1):
                seg = mask_mid & (vals >= ml[k]) & (vals < ml[k + 1])
                if seg.any():
                    result[seg] = fl[k] + (fl[k + 1] - fl[k]) * \
                                  (vals[seg] - ml[k]) / (ml[k + 1] - ml[k])

        for i in range(len(sd.sta_data)):
            sd.sta_data[i].val = float(result[i])
        return sd

    @staticmethod
    def _correct_grid(model_data, fact_level, model_level):
        gd = model_data.copy_grid_data()
        num = len(fact_level)
        if num == 0:
            return model_data
        v = model_data.val
        gv = gd.val
        ml0, mln = model_level[0], model_level[num - 1]
        # below level[0]
        mask_below = v < ml0
        if ml0 == 0.0:
            gv[mask_below] = 0.0
        else:
            gv[mask_below] = v[mask_below] * (fact_level[0] / ml0)
        # above level[-1]
        mask_above = v >= mln
        if mln == 0.0:
            gv[mask_above] = 0.0
        else:
            gv[mask_above] = v[mask_above] * (fact_level[num - 1] / mln)
        # between levels
        mask_mid = ~mask_below & ~mask_above
        if mask_mid.any():
            for k in range(num - 1):
                seg = mask_mid & (v >= model_level[k]) & (v < model_level[k + 1])
                if seg.any():
                    gv[seg] = fact_level[k] + (fact_level[k + 1] - fact_level[k]) * \
                              (v[seg] - model_level[k]) / (model_level[k + 1] - model_level[k])
        return gd

    @staticmethod
    def _correct_array(model_data, fact_level, model_level):
        num = len(fact_level)
        if num == 0:
            return model_data
        v = np.array(model_data, dtype=np.float64)
        result = np.empty_like(v)
        ml = np.array(model_level, dtype=np.float64)
        fl = np.array(fact_level, dtype=np.float64)

        # below level[0]
        mask_below = v < ml[0]
        if ml[0] == 0.0:
            result[mask_below] = 0.0
        else:
            result[mask_below] = v[mask_below] * (fl[0] / ml[0])

        # above level[-1]
        mask_above = v >= ml[-1]
        if ml[-1] == 0.0:
            result[mask_above] = 0.0
        else:
            result[mask_above] = v[mask_above] * (fl[-1] / ml[-1])

        # between levels
        mask_mid = ~mask_below & ~mask_above
        if mask_mid.any():
            for k in range(num - 1):
                seg = mask_mid & (v >= ml[k]) & (v < ml[k + 1])
                if seg.any():
                    result[seg] = fl[k] + (fl[k + 1] - fl[k]) * \
                                  (v[seg] - ml[k]) / (ml[k + 1] - ml[k])
        return result.tolist()
