# -*- coding: utf-8 -*-
"""集合相似：相关、RMSE、TS+Bias，按评分选出最像当前场的历史个例。"""
import math
import random
import numpy as np
from utils.types import GridData
from proc import alglib


class Ensemble:
    """历史场相对当前场的相似评分与排序。"""
    @staticmethod
    def similarity_score_by_corr(gd_model, gd_fact, rain_limit=0.0, smooth_num=0):
        """两场 Pearson 相关（先按 ``rain_limit`` 置零再平滑）。"""
        grid_data = gd_model.copy_grid_data()
        grid_data2 = gd_fact.copy_grid_data()
        grid_data.clear_to_num_less_than(0.0, rain_limit)
        grid_data2.clear_to_num_less_than(0.0, rain_limit)
        grid_data.smooth9(smooth_num)
        grid_data2.smooth9(smooth_num)
        arr = grid_data.val.ravel()
        arr2 = grid_data2.val.ravel()
        return alglib.pearsoncorr2(arr, arr2)

    @staticmethod
    def similarity_score_by_rmse(gd_model, gd_fact, rain_limit=0.0, smooth_num=0):
        """两场 RMSE（越小越相似）。"""
        grid_data = gd_model.copy_grid_data()
        grid_data2 = gd_fact.copy_grid_data()
        grid_data.clear_to_num_less_than(0.0, rain_limit)
        grid_data2.clear_to_num_less_than(0.0, rain_limit)
        grid_data.smooth9(smooth_num)
        grid_data2.smooth9(smooth_num)
        grid_data.sub_val(grid_data2)
        return float(np.sqrt(np.mean(grid_data.val ** 2)))

    @staticmethod
    def similarity_score_by_ts_and_bias(gd_model, gd_fact, rain_limit=0.0, smooth_num=0, check_limit=0.1):
        """\(s=\\mathrm{TS}(1+0.2/|9(\\mathrm{Bias}-1)|+1)\)；样本过少返回 -1。"""
        grid_data = gd_model.copy_grid_data()
        grid_data2 = gd_fact.copy_grid_data()
        grid_data.clear_to_num_less_than(0.0, rain_limit)
        grid_data2.clear_to_num_less_than(0.0, rain_limit)
        grid_data.smooth9(smooth_num)
        grid_data2.smooth9(smooth_num)
        v1 = grid_data.val
        v2 = grid_data2.val
        m_hit = v1 >= check_limit
        f_hit = v2 >= check_limit
        hits = float(np.sum(m_hit & f_hit))
        misses = float(np.sum(~m_hit & f_hit))
        false_alarms = float(np.sum(m_hit & ~f_hit))
        total = hits + misses + false_alarms
        if total <= 10.0:  # 有效格点过少，该阈值不可用
            return -1.0
        ts = hits / (total + 0.001)
        bias = (hits + false_alarms + 0.001) / (hits + misses + 0.001)
        return float(ts * (1.0 + 0.2 / (abs(9.0 * (bias - 1.0)) + 1.0)))

    @staticmethod
    def get_similarity_index_by_corr(gd_model, gd_fact, choose_num, rain_limit=0.0, smooth_num=0):
        """按相关从大到小返回前 ``choose_num`` 个下标与评分。"""
        arr = [0.0] * len(gd_model)
        arr2 = list(range(len(gd_model)))
        arr3 = [[0.0] * choose_num, [0.0] * choose_num]
        for j in range(len(gd_model)):
            arr[j] = Ensemble.similarity_score_by_corr(gd_model[j], gd_fact, rain_limit, smooth_num)
        pairs = sorted(zip(arr, arr2), key=lambda x: x[0], reverse=True)
        for k in range(choose_num):
            arr3[0][k] = pairs[k][1]
            arr3[1][k] = pairs[k][0]
        return arr3

    @staticmethod
    def get_similarity_index_by_rmse(gd_model, gd_fact, choose_num, rain_limit=0.0, smooth_num=0):
        """按 RMSE 从小到大返回前 ``choose_num`` 个下标与评分。"""
        arr = [0.0] * len(gd_model)
        arr2 = list(range(len(gd_model)))
        arr3 = [[0.0] * choose_num, [0.0] * choose_num]
        for j in range(len(gd_model)):
            arr[j] = Ensemble.similarity_score_by_rmse(gd_model[j], gd_fact, rain_limit, smooth_num)
        pairs = sorted(zip(arr, arr2), key=lambda x: x[0])
        for k in range(choose_num):
            arr3[0][k] = pairs[k][1]
            arr3[1][k] = pairs[k][0]
        return arr3

    @staticmethod
    def get_similarity_index_by_ts_and_bias(gd_model, gd_fact, choose_num, *args):
        """多阈值 TS+Bias 平均后从大到小排序；``args`` 可为阈值列表。"""
        if len(args) == 0:
            rain_limit = 0.0
            smooth_num = 0
            check_limit = 0.1
        elif len(args) == 1 and isinstance(args[0], list):
            check_limit = args[0]
            rain_limit = 0.0
            smooth_num = 0
        elif len(args) == 3:
            rain_limit = args[0]
            smooth_num = args[1]
            check_limit = args[2]
        else:
            rain_limit = 0.0
            smooth_num = 0
            check_limit = 0.1

        arr = [0.0] * len(gd_model)
        arr2 = list(range(len(gd_model)))
        arr3 = [[0.0] * choose_num, [0.0] * choose_num]

        if isinstance(check_limit, list):
            for j in range(len(gd_model)):
                arr[j] = 0.0
                count = 0.0
                for k in range(len(check_limit)):
                    score = Ensemble.similarity_score_by_ts_and_bias(
                        gd_model[j], gd_fact, rain_limit, smooth_num, check_limit[k])
                    if score >= 0.0:
                        arr[j] += score
                        count += 1.0
                if count > 0.0:
                    arr[j] /= count
                else:
                    arr[j] = 0.0
                arr2[j] = j
        else:
            for j in range(len(gd_model)):
                arr[j] = Ensemble.similarity_score_by_ts_and_bias(
                    gd_model[j], gd_fact, rain_limit, smooth_num, check_limit)
                if arr[j] < 0.0:
                    arr[j] = 0.0 + random.random() / 1000.0
                arr2[j] = j

        pairs = sorted(zip(arr, arr2), key=lambda x: x[0], reverse=True)
        for k in range(choose_num):
            arr3[0][k] = pairs[k][1]
            arr3[1][k] = pairs[k][0]
        return arr3
