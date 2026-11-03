#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MAIT 3h 算法插件：TS 动态加权、数据可用性、站点→格点 Cressman。

- ``AnalysisTsWeightProcess``：分区多阈值 TS → beta 平滑 → 加权融合 → 站点频率匹配
- ``DataFlgProcess``：历史/当前模式是否到齐
- ``StationDataInterp2GridDataProcess``：掩膜伪站 + Cressman + 格点频率匹配
"""
import numpy as np
import datetime
import meteva_base as meb
from utils.base_plugin import PostProcessingPlugin
from utils.util_new import copy_data, MetevaFrequencyMatch, data0_str, get_ts, StationDataArray, \
    MetevaSpatialAnalisis, bilinear_interpolation_from_grid_data


class AnalysisTsWeightProcess(PostProcessingPlugin):
    """分区计算多阈值 TS 权重，与历史 beta 平滑后加权融合当前场，再做站点频率匹配。"""
    def __init__(self, grid_base,
                 area_scale, model_num,
                 sd_before_model,
                 sd_current_model,
                 sd_sta_info, sd_fact,
                 sta_before_flg, model_name,
                 sta_current_flg, iflag_list, score_before_list):
        """``area_scale`` 为训练窗外扩；``iflag_list`` / ``score_before_list`` 来自历史 beta。"""

        self.grid_base = grid_base
        self.area_scale = area_scale
        self.model_num = model_num
        self.sd_before_model = sd_before_model
        self.sd_current_model = sd_current_model
        self.sd_sta_info = sd_sta_info
        self.sd_fact = sd_fact
        self.sta_before_flg = sta_before_flg
        self.model_name = model_name
        self.sta_current_flg = sta_current_flg
        self.iflag_list = iflag_list
        self.score_before_list = score_before_list

    def _analysis_ts_weight(self, grid_base, area_scale,
                            model_num,
                            sd_before_model, sd_current_model, sd_sta_info, sd_fact, sta_before_flg,
                            model_name,
                            sta_current_flg, iflag_list, score_before_list):
        """分区：多阈值 TS → \(s_{last}=(1-\\alpha)s_{before}+\\alpha s_{now}\) → 留前 5 → 加权融合 → 站点 FM。

        返回各子区的融合站点场列表与当期评分列表。
        """
        sd_output_list = []
        score_last_list = []
        lon_start = grid_base.slon
        lon_end = grid_base.elon
        lat_start = grid_base.slat
        lat_end = grid_base.elat
        lon_interval = [lon_end - lon_start]
        lat_interval = [lat_end - lat_start]
        # predict_valid = grid_base.dtimes[0]

        for i_num in range(len(lon_interval)):
            xxn = int((lon_end - lon_start) / lon_interval[i_num])
            yyn = int((lat_end - lat_start) / lat_interval[i_num])

            ii_sd_output_list = np.full(shape=(yyn, xxn), fill_value=0).tolist()
            ii_score_last_list = np.full(shape=(yyn, xxn), fill_value=0).tolist()

            for j in range(yyn):
                print("J Line Index: ", str(j + 1), '\n')
                for i in range(xxn):
                    sd_output = copy_data(sd_sta_info)
                    predict_point_lon = np.asarray([
                        lon_start + lon_interval[i_num] * i,
                        lon_start + lon_interval[i_num] * (i + 1),
                        lon_start + lon_interval[i_num] * (i + 1),
                        lon_start + lon_interval[i_num] * i
                    ])

                    predict_point_lat = np.asarray([
                        lat_start + lat_interval[i_num] * j,
                        lat_start + lat_interval[i_num] * j,
                        lat_start + lat_interval[i_num] * (j + 1),
                        lat_start + lat_interval[i_num] * (j + 1),
                    ])

                    # 训练窗外扩 area_scale，用窗外历史场/实况算 TS，预测区用当前场加权
                    train_point_lon = np.asarray([
                        lon_start + lon_interval[i_num] * i - lon_interval[i_num] * area_scale,
                        lon_start + lon_interval[i_num] * (i + 1) + lon_interval[
                            i_num] * area_scale,
                        lon_start + lon_interval[i_num] * (i + 1) + lon_interval[
                            i_num] * area_scale,
                        lon_start + lon_interval[i_num] * i - lon_interval[i_num] * area_scale,
                    ])

                    train_point_lat = np.asarray([
                        lat_start + lat_interval[i_num] * j - lat_interval[i_num] * area_scale,
                        lat_start + lat_interval[i_num] * j - lat_interval[i_num] * area_scale,
                        lat_start + lat_interval[i_num] * (j + 1) + lat_interval[
                            i_num] * area_scale,
                        lat_start + lat_interval[i_num] * (j + 1) + lat_interval[i_num] * area_scale
                    ])

                    sd_frame_current_model = list()
                    sd_frame_before_model = list()
                    for n in range(model_num):
                        sd_before_model_df_in = meb.sele_by_para(sd_before_model[n], lon=[train_point_lon[0],
                                                                                          train_point_lon[1]],
                                                                 lat=[train_point_lat[0],
                                                                      train_point_lat[2]])
                        sd_frame_before_model.append(sd_before_model_df_in)

                        sd_current_model_df_in = meb.sele_by_para(sd_current_model[n],
                                                                  lon=[train_point_lon[0],
                                                                       train_point_lon[1]],
                                                                  lat=[train_point_lat[0],
                                                                       train_point_lat[2]])
                        sd_frame_current_model.append(sd_current_model_df_in)
                    sd_frame_output = meb.sele_by_para(sd_sta_info,
                                                       lon=[train_point_lon[0], train_point_lon[1]],
                                                       lat=[train_point_lat[0], train_point_lat[2]])
                    sd_frame_output.iloc[:, -1] = 0.0
                    sd_frame_fact = meb.sele_by_para(sd_fact,
                                                     lon=[train_point_lon[0], train_point_lon[1]],
                                                     lat=[train_point_lat[0], train_point_lat[2]])

                    ################################################################################

                    ################################################################################
                    # 多量级 TS：准确率 / (交叉相似 + S)，再按量级权重合成 score_now
                    rain_limit = [0.1, 10.0, 25.0, 50.0]  # 针对优化的量级
                    rain_limit_weight = [0.05, 0.1, 0.35, 0.5]  # 量级的权重系数

                    model_final_weight = [0.0] * model_num  # 模式权重，最终需要计算的数值
                    # score_before = [0.0] * model_num  # 得分 score-before，之前得分
                    score_now = [0.0] * model_num  # 得分 score-now，现在得分
                    score_last = [0.0] * model_num  # 得分最终的 score-last
                    score_tmp = [0.0] * model_num  # 平均成绩，用于不同量级的标准化
                    ts_fact = [0.0] * model_num  # TS得分，表达预报准确率
                    ts_each = [[0.0] * model_num for _ in range(model_num)]  # 彼此TS得分，表示重复性
                    apha = 0.1  # 衰减系数（现在时刻评分的重要性）
                    similar_smooth = 100000.0  # 平滑参数 (用于决定相似的重要性)

                    # 计算过去1天的TS评分，len为4
                    for i_level in range(len(rain_limit_weight)):  # 预报等级循环
                        # 计算TS评分准确率，之前的预报和实况计算ts
                        num16 = 0
                        for i_model in range(model_num):
                            if sta_before_flg[i_model] == 1.0:  # 存在文件
                                ts_fact[i_model] = get_ts(
                                    sd_frame_before_model[i_model][data0_str].to_numpy(),
                                    sd_frame_fact[data0_str].to_numpy(),
                                    rain_limit[i_level], 20.0)

                                if ts_fact[i_model] >= 0.1:
                                    num16 = 1
                            else:  # 不存在文件
                                ts_fact[i_model] = 0.0
                        # 计算彼此之间的TS评分
                        for i_model in range(model_num):
                            for j_model in range(model_num):
                                if sta_before_flg[i_model] == 1.0 and sta_before_flg[j_model] == 1.0:
                                    ts_each[i_model][j_model] = get_ts(
                                        sd_frame_before_model[i_model][data0_str].to_numpy(),
                                        sd_frame_before_model[j_model][data0_str].to_numpy(),
                                        rain_limit[i_level], 20.0)
                                else:
                                    ts_each[i_model][j_model] = 0.0

                        # 计算当前score评分
                        scoreTotal = 0.0
                        for i_model in range(model_num):
                            e_ts = 0.0
                            for jModel in range(model_num):
                                e_ts += ts_each[i_model][jModel]
                            e_ts /= model_num  # 计算8个模式平均ts
                            score_tmp[i_model] = ts_fact[i_model] / (e_ts + similar_smooth)
                            scoreTotal += score_tmp[i_model]

                        # print("changed ts\n")
                        for i_model in range(model_num):
                            if scoreTotal != 0.0 and num16 == 1:  # 对某个量级存在可判断性
                                score_tmp[i_model] /= scoreTotal
                            else:  # 对某个量级无法判断，则大家权重一致
                                score_tmp[i_model] = 1.0 / model_num

                        for i_model in range(model_num):
                            score_now[i_model] += rain_limit_weight[i_level] * score_tmp[i_model]

                    print("score_now:")
                    iflag = iflag_list[i_num][j][i]
                    score_before = score_before_list[i_num][j][i]

                    # 获得过去评分，
                    if iflag == 0:
                        for n in range(model_num):
                            score_before[n] = score_now[n]
                    total_before = sum(score_before)  # 过去评分的均一化
                    if total_before == 0.0:
                        for n in range(model_num):  # 代表没有过去信息，现在计算信息就是过去信息
                            score_before[n] = score_now[n]
                    else:
                        for n in range(model_num):
                            score_before[n] /= total_before

                    # s_last = (1-α) s_before + α s_now
                    for n in range(model_num):
                        score_last[n] = (1.0 - apha) * score_before[n] + apha * score_now[n]

                    # # 输出权重系数
                    score_last_now = score_last.copy()
                    ii_score_last_list[j][i] = score_last_now
                    ################################################################################

                    ################################################################################
                    # 计算权重系数
                    array15 = list(range(model_num))
                    array16 = score_last[:model_num]
                    # 按照评分由小到大排序
                    array16, array15 = zip(*sorted(zip(array16, array15)))
                    array15 = list(reversed(array15))
                    array16 = list(reversed(array16))  # 倒叙排，按照由大到小

                    for num38 in range(5, model_num):  # 仅保留评分最高的 5 个模式
                        score_last[array15[num38]] = 0.0  # 将部分模式的平等置为0

                    stotal = 0.0  # 目的是当前模式数据可能有缺失，需要做调整
                    for n in range(model_num):
                        stotal += sta_current_flg[n] * score_last[
                            n]  # 模式数据存在的话，sta_current_flg[n]为1，不存在为0
                    for n in range(model_num):
                        model_final_weight[n] = (sta_current_flg[n] * score_last[n]) / (
                                stotal + 1e-4)  # 计算每个模式的权重值
                        print('model weight: ' + str(model_final_weight[n]))

                    ################################################################################
                    # V_sta = Σ w_n · V_now_n（缺测模式权重已为 0）
                    for md in range(model_num):
                        sd_frame_output_df_data = sd_frame_output[data0_str].to_numpy()
                        sd_frame_current_model_df_data = sd_frame_current_model[md][data0_str].to_numpy()

                        data11 = model_final_weight[md] * sd_frame_current_model_df_data
                        data12 = sd_frame_output_df_data + data11
                        sd_frame_output[data0_str] = data12

                    if len(sd_frame_output) != 0:
                        # 用保留模式的当前场对融合站点做分位映射订正
                        current_model_used = list()
                        output_used = list()
                        for n in range(model_num):
                            if sta_current_flg[n] == 1.0 and score_last[array15[n]] > 0.0:
                                current_model_used.append(sd_frame_current_model[array15[n]])
                                output_used.append(sd_frame_output)
                        print("number used: " + str(len(output_used)))
                        fact_level = [0.1, 0.5, 1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0,
                                      100.0, 150.0, 200.0, 250.0]
                        model_level = MetevaFrequencyMatch.get_model_level(output_used,
                                                                           current_model_used,
                                                                           fact_level)
                        sd_frame_output = MetevaFrequencyMatch.correct_model_data(sd_frame_output,
                                                                                  fact_level,
                                                                                  model_level[1])

                        sd_frame_output[data0_str][sd_frame_output[data0_str] < 0.1] = 0.0
                        sd_output = meb.sele_by_para(sd_output,
                                                     lon=[predict_point_lon[0],
                                                          predict_point_lon[1]],
                                                     lat=[predict_point_lat[0],
                                                          predict_point_lat[2]])
                        sd_output = sd_output.merge(
                            sd_frame_output[['id', data0_str]].rename(columns={data0_str: 'new_' + data0_str}),
                            on='id',
                            how='left'
                        )
                        sd_output[data0_str] = sd_output['new_' + data0_str].fillna(
                            sd_output[data0_str])
                        sd_output = sd_output.drop(columns=['new_' + data0_str])
                        ii_sd_output_list[j][i] = sd_output
            sd_output_list.append(ii_sd_output_list)
            score_last_list.append(ii_score_last_list)
        return sd_output_list, score_last_list

    def process(self):
        """返回整域融合站点场 ``sd_output`` 与当期评分 ``score_last``。"""
        sd_output_list, score_last_list = self._analysis_ts_weight(self.grid_base,
                                                                   self.area_scale,
                                                                   self.model_num,
                                                                   self.sd_before_model,
                                                                   self.sd_current_model,
                                                                   self.sd_sta_info,
                                                                   self.sd_fact,
                                                                   self.sta_before_flg,
                                                                   self.model_name,
                                                                   self.sta_current_flg,
                                                                   self.iflag_list,
                                                                   self.score_before_list)
        sd_output = sd_output_list[0][0][0]
        score_last = score_last_list[0][0][0]
        return sd_output, score_last


class StationDataInterp2GridDataProcess(PostProcessingPlugin):
    """订正站点 + 掩膜外背景伪站 → Cressman → 格点频率匹配 → 长时效衰减。"""

    def __init__(self, gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground, sd_output):
        self.gd_mask_val = gd_mask_val
        self.gd_mask_xn = gd_mask_xn
        self.gd_mask_yn = gd_mask_yn
        self.gd_back_ground = gd_back_ground
        self.sd_output = sd_output
        self.grid_base = grid_base

    def _m3_data_interp(self, gd_mask_val, gd_mask_xn, gd_mask_yn, gd_back_ground, sd_output,
                        grid_base):
        """境外伪站 + 订正站 → 多半径 Cressman → 格点频率匹配 → 长时效衰减。"""
        predict_valid = grid_base.dtimes[0]
        lt_valid_id_list = []
        lt_valid_lon_list = []
        lt_valid_lat_list = []
        lt_valid_data0_list = []

        # 掩膜<0 视为境外：每 5 点抽一个背景格点当伪站，减轻边界空洞
        for j in range(0, gd_mask_yn, 5):
            for i in range(0, gd_mask_xn, 5):
                # 中国区域外的点
                if gd_mask_val[i][j] < 0.0:
                    db_lon = gd_back_ground.lon[i]
                    db_lat = gd_back_ground.lat[j]
                    db_value = gd_back_ground.data[i][j]
                    db_id = str(int(db_lon * 1e2 + db_lat * 1e7)).zfill(11)

                    lt_valid_id_list.append(db_id)
                    lt_valid_lon_list.append(db_lon)
                    lt_valid_lat_list.append(db_lat)
                    lt_valid_data0_list.append(db_value)
        sd_id_list = sd_output['id']
        sd_lon_list = sd_output['lon']
        sd_lat_list = sd_output['lat']
        sd_data0_list = sd_output[data0_str]

        lt_valid_id_list.extend(sd_id_list)
        lt_valid_lon_list.extend(sd_lon_list)
        lt_valid_lat_list.extend(sd_lat_list)
        lt_valid_data0_list.extend(sd_data0_list)

        lt_valid_data = StationDataArray(lt_valid_id_list, lt_valid_lon_list, lt_valid_lat_list,
                                         lt_valid_data0_list)

        print("sta num for cressman:", str(len(lt_valid_id_list)))  # 15614

        # 影响半径按经距的 8/6/4/2 倍逐步订正
        gd_final_output = MetevaSpatialAnalisis.gressman_interpolation_for_rain(
            lt_valid_data,
            gd_back_ground,
            [
                8 * gd_back_ground.lon_interval,
                6 * gd_back_ground.lon_interval,
                4 * gd_back_ground.lon_interval,
                2 * gd_back_ground.lon_interval
            ], 1.0, 0.001, 2.0, 0.01)
        gd_final_output.smooth_9(10)  # 9 点平滑 10 次，削弱插值噪声

        sd_output = StationDataArray(sd_id_list, sd_lon_list, sd_lat_list, sd_data0_list)

        # 格点回插到站，与订正站建立分位映射后再订正格点
        sd_reference = copy_data(sd_output)
        sd_reference = bilinear_interpolation_from_grid_data(sd_reference, gd_final_output, 0.0)

        bg_fact_level = [0.01, 0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0,
                         150.0, 200.0, 250.0]
        bg_model_level = MetevaFrequencyMatch.get_used_model_level([sd_reference], [sd_output],
                                                                   bg_fact_level)

        if len(bg_model_level[0]) >= 2:
            gd_final_output = MetevaFrequencyMatch.correct_model_data(gd_final_output,
                                                                      bg_model_level[1],
                                                                      bg_model_level[0])
        else:
            gd_final_output = copy_data(gd_back_ground)

        if predict_valid >= 108:
            gd_final_output.multi_val(0.8)  # 长时效整体衰减
            gd_final_output.clear_to_num_greater_than(240.0, 250.0)
        gd_final_output.clear_to_num_less_than(0.0, 0.01)
        return gd_final_output

    def process(self):
        """返回订正后的格点场（供写 Micaps4）。"""
        gd_final_output = self._m3_data_interp(self.gd_mask_val, self.gd_mask_xn,
                                               self.gd_mask_yn,
                                               self.gd_back_ground, self.sd_output,
                                               self.grid_base)
        return gd_final_output

class DataFlgProcess(PostProcessingPlugin):
    """统计历史/当前模式到齐个数；全缺时后续集成应退出。"""

    def __init__(self, model_num, sta_before_flg, sta_current_flg2, simple_log):
        self.model_num = model_num
        self.sta_before_flg = sta_before_flg
        self.sta_current_flg2 = sta_current_flg2
        self.simple_log = simple_log

    def process(self):
        """返回 ``(历史到齐数, 当前到齐数, 当前各模式标记)``。"""
        sw = datetime.datetime.now()
        before_total_flg = 0.0  # 前期数值模式结果
        for i_model in range(self.model_num):
            if self.sta_before_flg[i_model] == 1.0:
                before_total_flg += 1.0
        if before_total_flg == 0.0:  # 如果之前模式结果都不存在，则无法进行集成
            print("All Before Data Is Not Exist!\n", flush=True)
            currentTotalFlg = 0.0
            # predict_valid += predict_interval
        ################################################################################
        # 读取当前模式资料
        else:
            end_time_read_micaps = datetime.datetime.now()
            time_elapsed_read_micaps = (end_time_read_micaps - sw).total_seconds()
            print('time_read_micap', time_elapsed_read_micaps)
            currentTotalFlg = sum(self.sta_current_flg2)
            if currentTotalFlg == 0.0:
                self.simple_log.error("All Current Data Is Not Exist!")
        return before_total_flg, currentTotalFlg, self.sta_current_flg2


