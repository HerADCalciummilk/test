# -- coding: utf-8 --
# @Time : 2025/1/22 13:33
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : cal_sliceTP.py
# @Software: PyCharm

from utils.config import *
from interpolation import *  # 原主程序的 Cressman / 双线性；nowcast 主程序会传入项目实现
from cal_optical_flow import OpticalFlow, Lagrangian  # correct_tp_24h 的光流；nowcast 主程序会传入项目实现
from cal_frequency_match import FrequencyMatch


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
        # 未传入时用本包原实现。correct_tp_24h_nowcast 传入项目实现。
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