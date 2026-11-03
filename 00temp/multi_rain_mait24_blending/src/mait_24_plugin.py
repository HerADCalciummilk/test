#!/usr/bin/env python

import numpy as np
import datetime
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
                 sd_current_model, sd_fact, sta_before_flg, sta_current_flg,
                 iflag_list, score_before_list, ctx: RunContext):
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

    @staticmethod
    def _analysis_ts_weight(grid_base, area_scale, model_num, sd_before_model, sd_current_model, sd_sta_info,
                            sd_fact, sta_before_flg, model_name, sta_current_flg, iflag_list, score_before_list,
                            split_lat, split_lon):
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
                    # 4) 根据时效设定 TS 评分阈值与权重
                    if predict_valid <= 60:
                        rain_limit = [0.10, 10.0, 25.0, 50.0]  # 短时效更关注暴雨
                        rain_limit_weight = [0.1, 0.15, 0.3, 0.45]  # 量级的权重系数
                    else:
                        rain_limit = [0.10, 10.0, 25.0, 50.0]
                        rain_limit_weight = [0.1, 0.2, 0.45, 0.25]  # 长时效加大中雨权重

                    model_final_weight = [0.0] * model_num  # 模式权重，最终需要计算的数值
                    # score_before = [0.0] * model_num  # 得分 score-before，之前得分
                    score_now = [0.0] * model_num  # 得分 score-now，现在得分
                    score_last = [0.0] * model_num  # 得分最终的 score-last
                    score_tmp = [0.0] * model_num  # 平均成绩，用于不同量级的标准化
                    ts_fact = [0.0] * model_num  # TS得分，表达预报准确率
                    ts_each = [[0.0] * model_num for _ in range(model_num)]  # 彼此TS得分，表示重复性
                    apha = 0.1  # 衰减系数（现在时刻评分的重要性）
                    similar_smooth = 100000.0  # 平滑参数 (用于决定相似的重要性)

                    # 5) 多量级 TS 评分循环
                    for i_level in range(len(rain_limit_weight)):  # 预报等级循环
                        # 5.1) 计算各模式 vs 实况的 TS
                        num16 = 0   # 标志：是否有模式 TS>=0.1
                        for i_model in range(model_num):
                            if sta_before_flg[i_model] == 1.0:  # 存在文件
                                ts_fact[i_model] = get_ts(
                                    sd_frame_before_model[i_model][data0_str].to_numpy(),
                                    sd_frame_fact[data0_str].to_numpy(),
                                    rain_limit[i_level], 10.0)

                                if ts_fact[i_model] >= 0.1:
                                    num16 = 1
                        # 5.2) 计算模式间两两 TS（衡量相似性/重复性）
                        for i_model in range(model_num):
                            for j_model in range(model_num):
                                if sta_before_flg[i_model] == 1.0 and sta_before_flg[j_model] == 1.0:
                                    ts_each[i_model][j_model] = get_ts(
                                        sd_frame_before_model[i_model][data0_str].to_numpy(),
                                        sd_frame_before_model[j_model][data0_str].to_numpy(),
                                        rain_limit[i_level], 10.0)
                                else:
                                    ts_each[i_model][j_model] = 0.0

                        # 5.3) 计算当前量级临时权重
                        scoreTotal = 0.0
                        for i_model in range(model_num):
                            e_ts = 0.0
                            for jModel in range(model_num):
                                e_ts += ts_each[i_model][jModel]
                            e_ts /= model_num  # 计算8个模式平均ts
                            score_tmp[i_model] = ts_fact[i_model] / (e_ts + similar_smooth)
                            scoreTotal += score_tmp[i_model]

                        # 归一化；若无可判性则均等权重
                        for i_model in range(model_num):
                            if scoreTotal != 0.0 and num16 == 1:  # 对某个量级存在可判断性
                                score_tmp[i_model] /= scoreTotal
                            else:  # 对某个量级无法判断，则大家权重一致
                                score_tmp[i_model] = 1.0 / model_num
                        # 5.4) 累加到 score_now
                        for i_model in range(model_num):
                            score_now[i_model] += rain_limit_weight[i_level] * score_tmp[i_model]

                    # 6) 融合历史评分
                    iflag = iflag_list[i_num][j][i]
                    score_before = score_before_list[i_num][j][i]

                    # 获得过去评分，
                    if iflag == 0:  # 首次无历史分，直接赋当前分
                        for n in range(model_num):
                            score_before[n] = score_now[n]
                    total_before = sum(score_before)  # 过去评分的均一化
                    if total_before == 0.0:
                        for n in range(model_num):  # 代表没有过去信息，现在计算信息就是过去信息
                            score_before[n] = score_now[n]
                    else:
                        for n in range(model_num):
                            score_before[n] /= total_before

                    # 7) 衰减融合得最终评分
                    for n in range(model_num):
                        score_last[n] = (1.0 - apha) * score_before[n] + apha * score_now[n]

                    # 8) 时效筛选：108-238h 仅保留 ecModel，其余保留前 3 名
                    score_last_now = score_last.copy()
                    ii_score_last_list[j][i] = score_last_now

                    # 计算权重系数
                    array15 = list(range(model_num))
                    array16 = score_last[:model_num]
                    # 按照评分由小到大排序
                    array16, array15 = zip(*sorted(zip(array16, array15)))
                    array15 = list(reversed(array15))
                    array16 = list(reversed(array16))  # 倒叙排，按照由大到小

                    if (predict_valid >= 108) and (predict_valid <= 238):
                        for num37 in range(model_num):
                            if model_name[array15[num37]] != "ecModel":
                                score_last[array15[num37]] = 0.0
                    else:
                        for num38 in range(5, model_num):  # [5,6,7]
                            score_last[array15[num38]] = 0.0  # 将部分模式的平等置为0

                    # 9) 按当前数据存在性再次归一化
                    stotal = 0.0  # 目的是当前模式数据可能有缺失，需要做调整
                    for n in range(model_num):
                        stotal += sta_current_flg[n] * score_last[
                            n]  # 模式数据存在的话，sta_current_flg[n]为1，不存在为0
                    for n in range(model_num):
                        model_final_weight[n] = (sta_current_flg[n] * score_last[n]) / (
                                stotal + 1e-6)  # 计算每个模式的权重值

                    # 10) 线性集成
                    for md in range(model_num):
                        sd_frame_output_df_data = sd_frame_output[data0_str].to_numpy()
                        sd_frame_current_model_df_data = sd_frame_current_model[md][data0_str].to_numpy()

                        data11 = model_final_weight[md] * sd_frame_current_model_df_data
                        data12 = sd_frame_output_df_data + data11
                        sd_frame_output[data0_str] = data12

                    if len(sd_frame_output) != 0:
                        # 11) 频率匹配订正
                        current_model_used = list()
                        output_used = list()
                        for n in range(model_num):
                            if sta_current_flg[n] == 1.0 and score_last[n] > 0.0:
                                for m in range(int(100 * model_final_weight[n])):
                                    current_model_used.append(sd_frame_current_model[n])
                                    output_used.append(sd_frame_output)
                        fact_level = [0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0,
                                      30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0]
                        model_level = MetevaFrequencyMatch.get_model_level(output_used,
                                                                           current_model_used,
                                                                           fact_level)
                        sd_frame_output = MetevaFrequencyMatch.correct_model_data(sd_frame_output,
                                                                                  fact_level,
                                                                                  model_level[1])

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


    def process(self):
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
                                                                self.split_lon)
        return sd_output_list, score_last_list


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

        # 3) Cressman 四半径逐步订正 → 初版网格
        gd_final_output = MetevaSpatialAnalisis.gressman_interpolation_for_rain(
            lt_valid_data,
            gd_back_ground,
            [
                8 * gd_back_ground.lon_interval,
                6 * gd_back_ground.lon_interval,
                4 * gd_back_ground.lon_interval,
                2 * gd_back_ground.lon_interval
            ], 1.0, 0.001, 2.0, 0.01)
        # 4) 9 点平滑 5 次，抑制插值噪声
        gd_final_output.smooth_9(5)

        sd_output = StationDataArray(sd_id_list, sd_lon_list, sd_lat_list, sd_data0_list)
        # 5) 频率匹配订正：把网格再校正到与实况相同的降水分布
        sd_reference = copy_data(sd_output)
        # 先用双线性把网格值插回站点，作为“参考”
        sd_reference = bilinear_interpolation_from_grid_data(sd_reference, gd_final_output, 0.0)

        bg_fact_level = [0.01, 0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0,
                         75.0, 100.0, 150.0, 200.0, 250.0]   # 19 个降水等级
        bg_model_level = MetevaFrequencyMatch.get_used_model_level([sd_reference], [sd_output],
                                                                   bg_fact_level)

        if len(bg_model_level[0]) >= 2:   # 样本充足才做匹配
            gd_final_output = MetevaFrequencyMatch.correct_model_data(gd_final_output,
                                                                      bg_model_level[1],
                                                                      bg_model_level[0])
        else:
            gd_final_output = copy_data(gd_back_ground)   # 样本不足→退回背景
        # 6) 长时效折减 & 极值处理
        if predict_valid >= 108:   # 108 h 以后暴雨空报倾向大
            gd_final_output.multi_val(0.8)   # 整体衰减 20 %
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
    """
    数据flg的类
    `DataFlgProcess.process` 是 MAIT 系统的**数据可用性守门员**，只做一件事：
    **统计“历史样本”和“当前时效”各模式数据到底在不在**，用两个浮点 flag 告诉下游能否继续走集成流程。
    1. 遍历 `sta_before_flg`
       把 ==1.0 的累加得到 `before_total_flg`；若最终为 0 → 所有历史样本缺失，直接打印告警并强制 `currentTotalFlg=0`，提前结束。
    2. 历史样本 OK 的前提下
       累加 `sta_current_flg2` 得到 `currentTotalFlg`，表示当前时效实际可用的模式个数；若仍为 0 → 写日志报错“All Current Data Is Not Exist!”。
    3. 返回三元组
       `(before_total_flg, currentTotalFlg, sta_current_flg2)`
       - 上游据此判断是否跳过集成
       - `_analysis_ts_weight` 用 `sta_current_flg2` 做“存在性加权”，缺失模式自动得 0 权重，无需人工干预。
    整个函数耗时极低，却避免了因数据空缺导致的崩溃或空报。
    """

    def __init__(self, model_num, sta_before_flg, sta_current_flg2, simple_log):
        self.model_num = model_num
        self.sta_before_flg = sta_before_flg
        self.sta_current_flg2 = sta_current_flg2
        self.simple_log = simple_log

    def process(self):
        sw = datetime.datetime.now()
        before_total_flg = 0.0  # 前期数值模式结果
        for i_model in range(self.model_num):
            if self.sta_before_flg[i_model] == 1.0:
                before_total_flg += 1.0

        if before_total_flg == 0.0:  # 如果之前模式结果都不存在，则无法进行集成
            print("> 1 All Before Data Is Not Exist!\n")
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
                # self.simple_log.error("All Current Data Is Not Exist!")
                pass
        return before_total_flg, currentTotalFlg, self.sta_current_flg2

