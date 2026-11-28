#!/usr/bin/env python

import numpy as np
import meteva_base as meb
# from nimm import PostProcessingPlugin
from utils.base_plugin import PostProcessingPlugin
from utils.util_context import RunContext
from utils.util_new import copy_data, MetevaFrequencyMatch, data0_str, get_ts, StationDataArray, \
    MetevaSpatialAnalisis, bilinear_interpolation_from_grid_data


class AnalysisTsWeightProcess(PostProcessingPlugin):
    """
    计算评分权重
    作用是在每个子格点、针对每个模式，动态算出**最优 TS 权重**，完成**多模式降水集成 + 频率匹配订正**。流程可概括为 8 步：
    1. 子格点训练区
       把全国按当前分辨率拆成 `(xxn, yyn)` 个小矩形；对每个小矩形向外扩 `area_scale` 倍格距，形成“训练区”，用于局部统计。
    2. 局部采样
       用 `sele_by_para` 一次性裁出训练区内的**实况**、**历史模式样本**、**当前模式场**和**空模板站点**，保证权重计算都在同一批站点上进行。
    3. 多量级 TS
       对 0.1 / 10 / 25 / 50 mm 四个阈值分别计算
       - `ts_fact`：各模式 vs 实况的 TS
       - `ts_each`：模式两两之间的 TS（衡量相似/重复）
       短时效（≤60 h）暴雨权重高，长时效加大中雨权重。
    4. 当前评分 `score_now`
       用“TS 越高、相似越低”原则给每个量级赋临时权重，再按 `rain_limit_weight` 加权合成 `score_now`。
    5. 历史记忆
       引入上一循环的 `score_before`，通过衰减系数 `α=0.1` 做指数平滑：
       `score_last = (1-α)*score_before + α*score_now`
       既保留历史优势，又及时反映最新表现。
    6. 时效筛选
       - 108–238 h：只保留 **ecModel** 权重，其余强制置 0
       - 其它时效：保留排序前 5 名，后几名置 0
       保证长时效以 ECMWF 为主，短时效充分利用多模式。
    7. 数据存在性校验
       用 `sta_current_flg` 再次归一化，缺失模式自动得 0 权重，**免人工干预**。
    8. 线性集成 + 频率匹配
       用 `model_final_weight` 对当前模式做**线性叠加**；随后按 0.01–250 mm 共 20 个等级做**频率匹配订正**，<0.01 mm 清零，最终输出**集成站点数据**和**下一轮要用的新评分矩阵**。
    返回的 `sd_output_list` 和 `score_last_list` 正好是下一个循环的输入，实现**滚动自适应**。
    """

    def __init__(self, grid_base, sd_before_model,
                 sd_current_model, sd_fact, sta_before_flg, sta_current_flg, iflag_list,
                 score_before_list, ctx: RunContext,
                 before_model_series=None, before_model_flag=None,
                 before_fact_series=None, before_fact_flag=None,
                 front_model=None, front_model_flag=None, front_fact=None):
        self.grid_base = grid_base
        self.area_scale = ctx.grid.area_scale
        self.sd_before_model = sd_before_model
        self.sd_current_model = sd_current_model
        self.sd_sta_info = ctx.session.sd_sta_info
        self.sd_fact = sd_fact
        self.sta_before_flg = sta_before_flg
        self.model_name = list(ctx.models.model_name)
        self.sta_current_flg = sta_current_flg
        self.iflag_list = iflag_list
        self.score_before_list = score_before_list
        self.model_num = len(self.model_name)
        self.split_lat = ctx.grid.split_lat
        self.split_lon = ctx.grid.split_lon
        self.before_model_series = before_model_series
        self.before_model_flag = before_model_flag
        self.before_fact_series = before_fact_series
        self.before_fact_flag = before_fact_flag
        self.front_model = front_model
        self.front_model_flag = front_model_flag
        self.front_fact = front_fact

    @staticmethod
    def _get_ts_series(predict_list, fact_list, level):
        return get_ts(predict_list, fact_list, level, 0.0)

    @staticmethod
    def _analysis_ts_weight(grid_base, area_scale, model_num, sd_before_model, sd_current_model, sd_sta_info,
                            sd_fact, sta_before_flg, model_name, sta_current_flg, iflag_list, score_before_list,
                            split_lat, split_lon, before_model_series=None, before_model_flag=None,
                            before_fact_series=None, before_fact_flag=None,
                            front_model=None, front_model_flag=None, front_fact=None):
        """
        基于 TS 评分动态计算各模式权重，完成多模式降水集成，并做频率匹配订正。
        主要步骤：
        1) 将研究区划分为若干子格点（i,j）；
        2) 对每个子格点，以 area_scale 扩展出训练区，提取对应站点数据；
        3) 针对 0.1/10/25/50 mm 四个量级分别计算 TS 评分，并加权得到当前时效评分 score_now；
        4) 利用衰减系数 α=0.1 将 score_now 与历史评分 score_before 融合，得到最终评分 score_last；
        5) 根据预报时效保留前 3 或仅保留 ecModel，再做数据存在性校验，归一化得到 model_final_weight；
        6) 用权重对各模式当前预报做线性集成；
        7) 基于 MetevaFrequencyMatch 做降水频率匹配订正，<0.01 mm 置 0；
        8) 返回集成后的站点数据 sd_output_list 与评分矩阵 score_last_list，供后续插值到网格。

        参数
        ----
        grid_base : GridBase
            包含起止经纬度、格距、预报时效 dtimes[0] 等基本信息。
        area_scale : int/float
            训练区相对预测区向外的“圈数”扩展倍数。
        model_num : int
            参与集成的模式总数。
        sd_before_model : list[DataFrame]
            每个模式历史同期样本的站点数据列表。
        sd_current_model : list[DataFrame]
            每个模式当前时效的站点数据列表。
        sd_sta_info : DataFrame
            空模板站点，用于保存集成结果。
        sd_fact : DataFrame
            对应时段的实况站点数据。
        model_name : list[str]
            模式名称，用于时效筛选逻辑。
        sta_before_flg : list[float]
            历史数据存在标志，1.0 存在，0.0 缺失。
        sta_current_flg : list[float]
            当前时效数据存在标志，1.0 存在，0.0 缺失。
        iflag_list : list[list[list[int]]]
            三维标志，记录每个子格点是否已有历史评分。
        score_before_list : list[list[list[list[float]]]]
            三维列表，记录每个子格点上一循环的历史评分向量。

        返回
        ----
        sd_output_list : list[list[DataFrame]]
            与空间网格对应的集成后站点数据。
        score_last_list : list[list[list[float]]]
            与空间网格对应的最终评分向量，供下一循环使用。
        """
        sd_output_list = []
        score_last_list = []
        lon_start = grid_base.slon
        lon_end = grid_base.elon
        lat_start = grid_base.slat
        lat_end = grid_base.elat
        lon_interval = [(lon_end - lon_start) / split_lon]
        lat_interval = [(lat_end - lat_start) / split_lat]
        predict_valid = grid_base.dtimes[0]  # 当前预报时效（小时）

        # 遍历所有格距方案（本实现仅 1 组）
        for i_num in range(len(lon_interval)):
            # 计算横向/纵向格点数
            xxn = int((lon_end - lon_start) / lon_interval[i_num])
            yyn = int((lat_end - lat_start) / lat_interval[i_num])

            # 预分配存储矩阵
            ii_sd_output_list = np.full(shape=(yyn, xxn), fill_value=0).tolist()
            ii_score_last_list = np.full(shape=(yyn, xxn), fill_value=0).tolist()
            # 逐子格点循环
            for j in range(yyn):
                for i in range(xxn):
                    # 1) 构造当前预测子区四角经纬度
                    _lons = [
                        lon_start + lon_interval[i_num] * i,
                        lon_start + lon_interval[i_num] * (i + 1),
                        lon_start + lon_interval[i_num] * (i + 1),
                        lon_start + lon_interval[i_num] * i
                    ]
                    _lats = [
                        lat_start + lat_interval[i_num] * j,
                        lat_start + lat_interval[i_num] * j,
                        lat_start + lat_interval[i_num] * (j + 1),
                        lat_start + lat_interval[i_num] * (j + 1),
                    ]
                    predict_point_lon = np.asarray(_lons)
                    predict_point_lat = np.asarray(_lats)

                    # 2) 构造训练区（向外扩展 area_scale 倍格距）
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
                    # 3) 按训练区裁剪各模式历史/当前样本及实况
                    sd_frame_current_model = list()
                    sd_frame_before_model = list()
                    _lat = [train_point_lat[0], train_point_lat[2]]
                    _lon = [train_point_lon[0], train_point_lon[1]]

                    for n in range(model_num):
                        sd_before_model_df_in = meb.sele_by_para(sd_before_model[n], lon=_lon, lat=_lat)
                        sd_frame_before_model.append(sd_before_model_df_in)

                        sd_current_model_df_in = meb.sele_by_para(sd_current_model[n], lon=_lon, lat=_lat)
                        sd_frame_current_model.append(sd_current_model_df_in)
                    sd_frame_output = meb.sele_by_para(sd_sta_info, lon=_lon, lat=_lat)
                    sd_frame_output.iloc[:, -1] = 0.0  # 初始化集成列
                    sd_frame_fact = meb.sele_by_para(sd_fact, lon=_lon, lat=_lat)

                    predict_point_lon = np.asarray(predict_point_lon)

                    ################################################################################

                    ################################################################################
                    rain_limit = [0.1, 1.0, 5.0, 10.0]
                    rain_limit_weight = [0.3, 0.2, 0.25, 0.25]

                    model_final_weight = np.zeros(model_num)
                    score_before = np.zeros(model_num)
                    score_now = np.zeros(model_num)
                    eps = 0.02

                    # 历史 10 日序列 TS
                    for i_level, tw in enumerate(rain_limit_weight):
                        source = np.zeros(model_num)
                        for i_model in range(model_num):
                            pred_hist = []
                            fact_hist = []
                            if before_model_series is not None and before_fact_series is not None:
                                for k in range(len(before_fact_series)):
                                    if before_model_flag is not None and before_fact_flag is not None:
                                        if before_model_flag[i_model, k] != 1.0 or before_fact_flag[k] != 1.0:
                                            continue
                                    p_df = meb.sele_by_para(before_model_series[i_model][k], lon=_lon, lat=_lat)
                                    f_df = meb.sele_by_para(before_fact_series[k], lon=_lon, lat=_lat)
                                    if len(p_df) == 0 or len(f_df) == 0:
                                        continue
                                    pred_hist.append(p_df[data0_str].to_numpy())
                                    fact_hist.append(f_df[data0_str].to_numpy())
                            if len(pred_hist) > 0:
                                source[i_model] = AnalysisTsWeightProcess._get_ts_series(
                                    pred_hist, fact_hist, rain_limit[i_level]
                                ) + eps
                        s = source.sum()
                        score_before += tw * (source / s if s > 0 else np.ones(model_num) / model_num)

                    # 前 1 小时 front 样本 TS
                    for i_level, tw in enumerate(rain_limit_weight):
                        source = np.zeros(model_num)
                        for i_model in range(model_num):
                            if front_model is not None and front_fact is not None and front_model_flag is not None and front_model_flag[i_model] == 1.0:
                                front_model_df = meb.sele_by_para(front_model[i_model], lon=_lon, lat=_lat)
                                front_fact_df = meb.sele_by_para(front_fact, lon=_lon, lat=_lat)
                                if len(front_model_df) == 0 or len(front_fact_df) == 0:
                                    continue
                                source[i_model] = get_ts(
                                    front_model_df[data0_str].to_numpy(),
                                    front_fact_df[data0_str].to_numpy(),
                                    rain_limit[i_level], 0.0
                                ) + eps
                        s = source.sum()
                        score_now += tw * (source / s if s > 0 else np.ones(model_num) / model_num)

                    score_last = 0.5 * score_before + 0.5 * score_now
                    ii_score_last_list[j][i] = score_last.tolist()

                    stotal = float(np.sum(sta_current_flg * score_last))
                    if stotal <= 0:
                        model_final_weight[:] = sta_current_flg / (np.sum(sta_current_flg) + 1e-6)
                    else:
                        model_final_weight[:] = (sta_current_flg * score_last) / (stotal + 1e-6)

                    # 10) 线性集成
                    for md in range(model_num):
                        sd_frame_output_df_data = sd_frame_output[data0_str].to_numpy()
                        sd_frame_current_model_df_data = sd_frame_current_model[md][data0_str].to_numpy()

                        data11 = model_final_weight[md] * sd_frame_current_model_df_data
                        data12 = sd_frame_output_df_data + data11
                        sd_frame_output[data0_str] = data12

                    if len(sd_frame_output) != 0:
                        # 11) 频率匹配订正（按 mait_st 流程：used_level + extend）
                        current_model_used = []
                        output_used = []
                        for n in range(model_num):
                            if sta_current_flg[n] == 1.0 and model_final_weight[n] > 0.0:
                                current_model_used.append(sd_frame_current_model[n])
                                output_used.append(sd_frame_output)
                        fact_level = [0.1, 0.5, 1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0]
                        used_model_level = MetevaFrequencyMatch.get_used_model_level_and_extend(
                            output_used, current_model_used, fact_level
                        )
                        if len(used_model_level[0]) >= 2:
                            sd_frame_output = MetevaFrequencyMatch.correct_model_data(
                                sd_frame_output,
                                used_model_level[1],
                                used_model_level[0]
                            )

                        sd_frame_output[data0_str][sd_frame_output[data0_str] < 0.01] = 0.0
                        sd_frame_output = meb.sele_by_para(sd_frame_output,
                                                           lon=[predict_point_lon[0],
                                                                predict_point_lon[1]],
                                                           lat=[predict_point_lat[0],
                                                                predict_point_lat[2]])
                        sd_output = sd_frame_output
                        ii_sd_output_list[j][i] = sd_output
            sd_output_list.append(ii_sd_output_list)
            score_last_list.append(ii_score_last_list)

        return sd_output_list, score_last_list


    def analysis_ts_weight(self):
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
                                                                self.score_before_list,
                                                                self.split_lat,
                                                                self.split_lon,
                                                                self.before_model_series,
                                                                self.before_model_flag,
                                                                self.before_fact_series,
                                                                self.before_fact_flag,
                                                                self.front_model,
                                                                self.front_model_flag,
                                                                self.front_fact)
        return sd_output_list, score_last_list


    def process(self):
        #  计算ts权重
        sd_output_list, score_last_list = self.analysis_ts_weight()
        # sd_output = sd_output_list[0][0][0]
        # score_last = score_last_list[0][0][0]

        sd_output = sd_output_list
        score_last = score_last_list
        return sd_output, score_last


class StationDataInterp2GridDataProcess(PostProcessingPlugin):
    """
       站点数据插值生成网格数据

       把**集成后的站点降水数据**（`sd_output`）融合**背景场**（`gd_back_ground`）并插值成**最终 MICAPS4 网格产品**。流程可概括为 6 步：
       1. 构造“外圈”背景点
          按 5×5 网格稀疏采样，把中国区域外（`gd_mask_val[i][j] < 0`）的背景格点值加入列表，作为后续插值的“外部约束”。
       2. 合并站点与背景
          将上一步的背景点与集成站点 `sd_output` 拼成一份完整 `StationDataArray`，保证后续插值既有观测也有外部信息。
       3. Cressman 逐步插值
          调用 `MetevaSpatialAnalisis.gressman_interpolation_for_rain`，用 4 个递减半径（8/6/4/2 倍格距）做逐步订正，得到初版网格 `gd_final_output`；随后做 5 次 9 点平滑，抑制噪声。
       4. 双线性采样 → 频率匹配
          用双线性插值把站点值重采样到网格，生成“参考站点”`sd_reference`；再与原始站点一起传入 `MetevaFrequencyMatch`，按 0.01–250 mm 共 19 个降水等级做频率校正，使网格降水分布与实况统计一致。
       5. 长时效折减与极值处理
          当预报时效 ≥108 h 时，整体乘以 0.8 的“衰减系数”并做 240 mm 封顶，降低长时效暴雨空报。
       6. 负值/小值清理
          把小于 0.01 mm 的值置 0，确保物理意义合理，最终返回可用于 MICAPS 显示的网格对象 `gd_final_output`。

       """

    def __init__(self, gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground,
                 sd_output):
        self.gd_mask_val = gd_mask_val
        self.gd_mask_xn = gd_mask_xn
        self.gd_mask_yn = gd_mask_yn
        self.gd_back_ground = gd_back_ground
        self.sd_output = sd_output
        self.grid_base = grid_base

    def _m3_data_interp(self, gd_mask_val, gd_mask_xn, gd_mask_yn, gd_back_ground, sd_output, grid_base):
        """
        将集成后的站点降水资料与背景场融合，经 Cressman 逐步插值 + 频率匹配 + 长时效折减，
        生成可供 MICAPS4 直接调用的最终网格产品。

        参数
        ----
        gd_mask_val : 2-D ndarray
            掩码矩阵，<0 表示中国区域外（无需预报但需背景约束）。
        gd_mask_xn, gd_mask_yn : int
            掩码矩阵的横向/纵向格点数。
        gd_back_ground : GridData
            背景格点场（一般为模式原始场或上一轮网格），提供经纬度模板与外部值。
        sd_output : DataFrame
            经过 _analysis_ts_weight 集成后的站点序列，含 id/lon/lat/data0。
        grid_base : GridBase
            包含预报时效 dtimes[0] 等元信息。

        返回
        ----
        gd_final_output : GridData
            已做平滑、频率匹配、长时效折减及小值清零的最终网格场。
        """
        predict_valid = grid_base.dtimes[0]  # 当前预报时效（h）
        # 1) 收集中国区域外的背景点（稀疏 5×5 采样），作为外圈约束
        lt_valid_id_list, lt_valid_lon_list, lt_valid_lat_list, lt_valid_data0_list = [], [], [], []

        for j in range(0, gd_mask_yn, 5):
            for i in range(0, gd_mask_xn, 5):
                if gd_mask_val[i][j] < 0.0:   # 掩码负值→海区/国外
                    db_lon = gd_back_ground.lon[i]
                    db_lat = gd_back_ground.lat[j]
                    db_value = gd_back_ground.data[i][j]
                    db_id = str(int(db_lon * 1e2 + db_lat * 1e7)).zfill(11)

                    lt_valid_id_list.append(db_id)
                    lt_valid_lon_list.append(db_lon)
                    lt_valid_lat_list.append(db_lat)
                    lt_valid_data0_list.append(db_value)   # data0_str 为降水字段名

        # 2) 合并集成站点与背景点，形成完整“观测”序列
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

        gd_final_output = MetevaSpatialAnalisis.gressman_interpolation_for_rain(
            lt_valid_data,
            gd_back_ground,
            [0.6, 0.4, 0.2, 0.1], 1.0, 0.001, 2.0, 0.01)
        gd_final_output.smooth_9(10)

        sd_output = StationDataArray(sd_id_list, sd_lon_list, sd_lat_list, sd_data0_list)
        # 5) 频率匹配订正：把网格再校正到与实况相同的降水分布
        sd_reference = copy_data(sd_output)
        # 先用双线性把网格值插回站点，作为“参考”
        sd_reference = bilinear_interpolation_from_grid_data(sd_reference, gd_final_output, 0.0)

        bg_fact_level = [0.01, 0.1, 0.5, 1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0]
        bg_model_level = MetevaFrequencyMatch.get_used_model_level([sd_reference], [sd_output],
                                                                   bg_fact_level)

        if len(bg_model_level[0]) >= 2:
            gd_final_output = MetevaFrequencyMatch.correct_model_data(gd_final_output,
                                                                      bg_model_level[1],
                                                                      bg_model_level[0])
        # 样本不足时保留 Cressman 结果（与 mait_st app.py 一致，不退回背景场）
        # 6) 1小时预报不做长时效折减，只做极值处理
        gd_final_output.clear_to_num_greater_than(240.0, 250.0)  # ≥240 强制=250

        # 7) 物理意义清理
        gd_final_output.clear_to_num_less_than(0.0, 0.01)  # <0.01 置 0
        return gd_final_output

    def process(self):
        # 插值
        gd_final_output = self._m3_data_interp(self.gd_mask_val, self.gd_mask_xn,
                                               self.gd_mask_yn,
                                               self.gd_back_ground, self.sd_output,
                                               self.grid_base)
        return gd_final_output


class DataFlgProcess(PostProcessingPlugin):
    """统计历史/当前模式数据可用性；历史全缺时不中断，由上游决定是否跳过时效。"""

    def __init__(self, sta_before_flg, sta_current_flg2, ctx: RunContext):
        self.model_num = len(ctx.models.model_name)
        self.sta_before_flg = sta_before_flg
        self.sta_current_flg2 = sta_current_flg2
        self.simple_log = ctx.session.simple_log

    def process(self):
        before_total_flg = 0.0
        for i_model in range(self.model_num):
            if self.sta_before_flg[i_model] == 1.0:
                before_total_flg += 1.0

        if before_total_flg == 0.0 and self.simple_log is not None:
            self.simple_log.info("All Before Data Is Not Exist!")
        elif before_total_flg == 0.0:
            print("All Before Data Is Not Exist!\n")

        currentTotalFlg = sum(self.sta_current_flg2)
        return before_total_flg, currentTotalFlg, self.sta_current_flg2


