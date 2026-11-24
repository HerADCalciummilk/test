import os
import sys

import meteva.base as meb
import numpy as np
import pandas as pd
import xarray as xr

from interpolation import GressManInterpolation, bilinear_interp, mesh_val
from utils.config import (
    fact_level,
    fact_level1,
    inter_dis,
    res,
    similar_level,
    smooth_num,
    sum_similar_threshold,
)
from utils.data_proc import (
    MultiValFormNewGridData,
    StandardizeByMaxMin,
    clear_to_num_greater_than,
    clear_to_num_less_than,
    clear_to_num_less_than_grd,
    creat_M3_grd,
    select_by_extend,
    smooth9,
    subtilize_grd,
)
from utils.logger import logger

# 直接从同级 optical_flow_nowcast 取原版估速/搬雨；临时插路径，避免抢本包 utils
_HERE = os.path.dirname(os.path.abspath(__file__))
_OF_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", "optical_flow_nowcast"))
_saved_utils = {
    k: sys.modules.pop(k)
    for k in list(sys.modules)
    if k == "utils" or k.startswith("utils.")
}
_path_before = list(sys.path)
try:
    while _OF_ROOT in sys.path:
        sys.path.remove(_OF_ROOT)
    sys.path.insert(0, _OF_ROOT)
    from src.lagrangian_plugin import Lagrangian  # noqa: E402
    from src.lsqr_optical_flow_plugin import OpticalFlow  # noqa: E402
finally:
    sys.path[:] = _path_before
    for k in list(sys.modules):
        if k == "utils" or k.startswith("utils."):
            if k not in _saved_utils:
                del sys.modules[k]
    sys.modules.update(_saved_utils)
del _saved_utils, _path_before, _HERE, _OF_ROOT

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


class correct_by_opticalFlow:

    def __init__(self, similarity_index, ext_extend, grd_hislist_model, grd_hislist_model_smooth, sta_hislist_obs,
                 optical_flow_cls=None, lagrangian_cls=None, cressman_fn=None,
                 mesh_val_fn=None, bilinear_fn=None):
        self.grd_hislist_model = grd_hislist_model
        self.grd_hislist_model_smooth = grd_hislist_model_smooth
        self.sta_hislist_obs = sta_hislist_obs
        self.ext_extend = ext_extend
        self.grd_01res = ext_extend + [res * 1]
        self.grd_05res = ext_extend + [res * 5]
        self.similarity_index = similarity_index
        self.similar_lenth = self._cal_similar_lenth()
        # 未传入时用本包原实现。
        self.optical_flow_cls = OpticalFlow if optical_flow_cls is None else optical_flow_cls
        self.lagrangian_cls = Lagrangian if lagrangian_cls is None else lagrangian_cls
        self.cressman_fn = GressManInterpolation if cressman_fn is None else cressman_fn
        self.mesh_val_fn = mesh_val if mesh_val_fn is None else mesh_val_fn
        self.bilinear_fn = bilinear_interp if bilinear_fn is None else bilinear_fn

    def _cal_similar_lenth(self):
        sum_similar = 0
        similar_lenth = 0
        for i in range(len(self.similarity_index[0])):
            sum_similar += self.similarity_index[1][i]
            similar_lenth += 1
            if sum_similar > sum_similar_threshold:
                break
        return similar_lenth

    def gain_his_slice(self, i):
        grd_model_smooth = self.grd_hislist_model_smooth[int(self.similarity_index[0][i])]
        grd_model = self.grd_hislist_model[int(self.similarity_index[0][i])]
        sta_obs = self.sta_hislist_obs[int(self.similarity_index[0][i])]

        sta_obs_cressman = self.cressman_fn(sta_obs, grd_model, [1.0, 0.8, 0.6, 0.4], rain_limit=0.01)
        grd_obs_smooth = smooth9(sta_obs_cressman, smooth_num)
        grd_obs_smooth = self.mesh_val_fn(grd_obs_smooth, self.grd_01res)
        grd_model_smooth_slice = self.mesh_val_fn(grd_model_smooth, self.grd_01res)

        FrequencyMatchObj = FrequencyMatch([grd_model_smooth_slice], [grd_obs_smooth], fact_level)
        model_level_and_extend = FrequencyMatchObj.get_used_model_level_and_extend('grd')
        if len(model_level_and_extend[0]) >= 2:
            grd_model_smooth_slice = FrequencyMatch.correct_model_grid(grd_model_smooth_slice, model_level_and_extend)

        return self.mesh_val_fn(grd_model_smooth_slice, self.grd_01res), self.mesh_val_fn(grd_obs_smooth, self.grd_01res)

    def gain_opticalFlow(self):
        grid_info_slice = self.mesh_val_fn(self.grd_hislist_model_smooth[0], self.grd_01res) * 0
        flowGrid = [grid_info_slice.copy(), grid_info_slice.copy()]

        _length = min(20, self.similar_lenth)
        grd_model_list = []
        grd_obs_list = []
        min_window = [[5.0, 5.0]]

        for index in range(_length):
            grd_model, grd_obs = self.gain_his_slice(index)
            grd_model_list.append(grd_model)
            grd_obs_list.append(grd_obs)

        self.optical_flow_cls.get_optical_flow(grd_model_list, grd_obs_list, min_window, flowGrid, rain_limit=25, num_limit=50)
        flowGrid[0] = self.mesh_val_fn(flowGrid[0], self.grd_01res)
        flowGrid[1] = self.mesh_val_fn(flowGrid[1], self.grd_01res)
        return flowGrid

    def correct_sliceTP(self, dtime, sta_ext, grd_current_model, grd_current_model_smooth):
        to_exclusive = max(int(0.5 * len(self.sta_hislist_obs)), self.similar_lenth)
        sd_sentive_model_list = []
        sd_sentive_fact_list = []
        for j in range(to_exclusive):
            sentive_model = self.mesh_val_fn(self.grd_hislist_model_smooth[int(self.similarity_index[0][j])], self.grd_01res)
            sd_sentive_model_list.append(self.bilinear_fn(sentive_model, sta_ext))
            sd_sentive_fact_list.append(select_by_extend(self.sta_hislist_obs[int(self.similarity_index[0][j])], self.ext_extend))
        FrequencyMatchOBJ = FrequencyMatch(sd_sentive_model_list, sd_sentive_fact_list, fact_level, 5)
        model_level_and_extend = FrequencyMatchOBJ.get_used_model_level_and_extend('sta')

        if len(model_level_and_extend[0]) < 2:
            correct_current_model = self.mesh_val_fn(grd_current_model, self.grd_01res)
        else:
            current_model = self.mesh_val_fn(grd_current_model_smooth, self.grd_01res)
            correct_current_model = FrequencyMatch.correct_model_grid(current_model, model_level_and_extend)

        if dtime <= 60:
            flowGrid = self.gain_opticalFlow()
            _Standardize_model = StandardizeByMaxMin(correct_current_model.copy(), 10.0, 25.0)
            u_Grid = MultiValFormNewGridData(flowGrid[0], _Standardize_model)
            v_Grid = MultiValFormNewGridData(flowGrid[1], _Standardize_model)
            correct_current_model = self.lagrangian_cls.simple_semi_lagrangian_in_angle(u_Grid, v_Grid, correct_current_model, 1.0)

        return correct_current_model


class OpticalFlowSliceCorrectPlugin:
    """分块光流订正：similarity → correct_by_opticalFlow（估 UV + 外推 + 块内 Cressman）。"""

    def __init__(self, dataset, cressman_fn, lagrangian_cls, optical_flow_cls=None):
        self.dataset = dataset
        self.cressman_fn = cressman_fn
        self.lagrangian_cls = lagrangian_cls
        self.optical_flow_cls = OpticalFlow if optical_flow_cls is None else optical_flow_cls

    def process(self):
        """返回合并后的订正站点场（含 time/dtime）；无有效切片时返回 None。"""
        dataset = self.dataset
        correct_slice_sta_list = []
        mask_array = dataset["mask_array"].copy()
        mask_array[mask_array <= 0] = 0
        for lat_index, lat_bottom in enumerate(dataset["center_lat_bottom"]):
            for lon_index, lon_left in enumerate(dataset["center_lon_left"]):
                try:
                    org_extend = [
                        lon_left,
                        dataset["center_lon_right"][lon_index],
                        lat_bottom,
                        dataset["center_lat_top"][lat_index],
                    ]
                    ext_extend = [
                        dataset["large_lon_left"][lon_index],
                        dataset["large_lon_right"][lon_index],
                        dataset["large_lat_bottom"][lat_index],
                        dataset["large_lat_top"][lat_index],
                    ]
                    sta_block = select_by_extend(dataset["sta_info"], org_extend)
                    if len(sta_block) <= 0:
                        continue
                    grd_05res = ext_extend + [dataset["res"] * 5]
                    current_model_slice = mesh_val(
                        dataset["grd_current_model_smooth"] * mask_array, grd_05res
                    )
                    history_model_slice = [
                        mesh_val(grd_smooth * mask_array, grd_05res)
                        for grd_smooth in dataset["grd_hislist_model_smooth"]
                    ]
                    similarity_index = similarity(
                        history_model_slice, current_model_slice, similar_level
                    ).get_similarity_index()
                    correct_current_model = correct_by_opticalFlow(
                        similarity_index,
                        ext_extend,
                        dataset["grd_hislist_model"],
                        dataset["grd_hislist_model_smooth"],
                        dataset["sta_hislist_obs"],
                        optical_flow_cls=self.optical_flow_cls,
                        lagrangian_cls=self.lagrangian_cls,
                        cressman_fn=self.cressman_fn,
                        mesh_val_fn=mesh_val,
                        bilinear_fn=bilinear_interp,
                    ).correct_sliceTP(
                        dataset["dtime"],
                        select_by_extend(dataset["sta_info"], ext_extend),
                        dataset["grd_current_model"],
                        dataset["grd_current_model_smooth"],
                    )
                    correct_slice_sta_list.append(
                        clear_to_num_less_than(
                            bilinear_interp(correct_current_model, sta_block), 0.0, 0.01
                        )
                    )
                except Exception as exc:
                    logger.error(
                        "切片订正失败 lon=%s lat=%s: %s",
                        lon_left,
                        lat_bottom,
                        exc,
                        exc_info=True,
                    )

        if not correct_slice_sta_list:
            return None
        sta_extend = [
            dataset["center_lon_left"][0],
            dataset["center_lon_right"][-1],
            dataset["center_lat_bottom"][0],
            dataset["center_lat_top"][-1],
        ]
        correct_sta = clear_to_num_less_than(
            select_by_extend(
                pd.concat(correct_slice_sta_list, ignore_index=True), sta_extend
            ),
            0.0,
            0.01,
        )
        correct_sta.time = dataset["rpt"]
        correct_sta.dtime = dataset["dtime"]
        return correct_sta


class CressmanFreqMatchGridPlugin:
    """整域插值订正：Cressman（或再处理）+ FrequencyMatch；无光流。"""

    def __init__(self, dataset, correct_sta, cressman_fn):
        self.dataset = dataset
        self.correct_sta = correct_sta
        self.cressman_fn = cressman_fn

    def process(self):
        """返回频率匹配后的订正格点场。"""
        dataset = self.dataset
        correct_sta = select_by_extend(
            self.correct_sta,
            [dataset["slon"], dataset["elon"], dataset["slat"], dataset["elat"]],
        )
        grd_current_model = mesh_val(dataset["grd_current_model"], dataset["inter"])
        lon, lat, data = subtilize_grd(
            dataset["grd_current_model"], dataset["mask_array"], inter_dis
        )
        current_model_sta = select_by_extend(
            creat_M3_grd(lon, lat, data, dataset["rpt"], dtime=dataset["dtime"]),
            [dataset["slon"], dataset["elon"], dataset["slat"], dataset["elat"]],
        )
        current_model_sta_add = pd.concat(
            [correct_sta, current_model_sta], ignore_index=True
        )
        current_model_grd = smooth9(
            self.cressman_fn(
                current_model_sta_add,
                grd_current_model,
                [0.8, 0.6, 0.4, 0.2],
                rain_limit=0.01,
            ),
            10,
        )
        used_model_level = FrequencyMatch(
            [
                bilinear_interp(
                    current_model_grd, clear_to_num_greater_than(correct_sta, 0, 0)
                )
            ],
            [correct_sta],
            fact_level1,
        ).get_used_model_level_and_extend("grd")
        print(used_model_level)
        return clear_to_num_less_than_grd(
            FrequencyMatch.correct_model_grid(current_model_grd, used_model_level),
            0.0,
            0.01,
        )
