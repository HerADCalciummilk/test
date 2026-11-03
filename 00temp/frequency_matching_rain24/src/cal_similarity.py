# -- coding: utf-8 --
# @Time : 2025/1/20 10:51
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : cal_similarity.py
# @Software: PyCharm
import numpy as np
import xarray as xr
from utils.data_proc import clear_to_num_less_than_grd

class similarity:

    def __init__(self, model_hislist, now_model, check_level, rain_limit=0.0):

        self.model_hislist = model_hislist
        self.now_model = now_model
        self.check_level_list = check_level
        self.rain_limit = rain_limit
        self.his_lenth = len(model_hislist)

    def similarity_score_by_ts_and_bias(self, his_model: xr.DataArray, now_model: xr.DataArray, rain_limit=0.0, check_level=0.1):
        his_model_filter = clear_to_num_less_than_grd(his_model, 0.0, rain_limit)
        now_model_filter = clear_to_num_less_than_grd(now_model, 0.0, rain_limit)
        now_model_array = now_model_filter.data.squeeze()
        his_model_array = his_model_filter.data.squeeze()

        bool_now = np.where(now_model_array >= check_level, 1, 0)
        bool_his = np.where(his_model_array >= check_level, 1, 0)
        num1 = np.sum(np.where((bool_now == 1) & (bool_his == 1), 1, 0))
        num2 = np.sum(np.where((bool_now == 1) & (bool_his == 0), 1, 0))
        num3 = np.sum(np.where((bool_now == 0) & (bool_his == 1), 1, 0))

        c = 1.0 + 0.2 / (abs(9.0 * ((num1 + num3 + 0.001) / (num1 + num2 + 0.001) - 1.0)) + 1.0)
        score = num1 / (num1 + num2 + num3 + 0.001) * c
        if num1 + num2 + num3 <= 10.0:
            score = -1.0

        return score

    def get_similarity_index(self):
        index_list = np.zeros(self.his_lenth).astype(int)
        score_list = np.zeros(self.his_lenth)

        for index1 in range(self.his_lenth):
            num1 = 0.0
            for index2 in range(len(self.check_level_list)):
                score = self.similarity_score_by_ts_and_bias(self.model_hislist[index1], self.now_model, self.rain_limit,
                                                             self.check_level_list[index2])
                if score >= 0.0:
                    score_list[index1] += score
                    num1 += 1

            if num1 > 0.0:
                score_list[index1] = score_list[index1] / num1
            else:
                score_list[index1] = 0.0
            index_list[index1] = index1

        similarity_index = [list(x) for x in zip(*sorted(zip(index_list, score_list), key=lambda x: x[1], reverse=True))]
        return similarity_index