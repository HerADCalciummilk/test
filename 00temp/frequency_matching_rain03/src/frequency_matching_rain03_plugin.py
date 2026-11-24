# -*- coding: utf-8 -*-
"""逐 3 小时降水频率匹配：核心订正插件。

``FrequencyMatchingRain03Plugin.process`` = 原 CLI ``correct_one_lead`` /
历史相似 → 频率匹配 →（短时效）光流外推 → Cressman 上格点 → 再 FM → 写出。
"""
from __future__ import annotations

import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import numpy as np

from proc import (
    Ensemble,
    FrequencyMatch,
    OpticalFlow,
    RainExtrapolation,
    SpatialAnalisis,
    StringProcess,
)
from utils.io_meb import expand_data_path, find_grid_file, find_sta_file
from utils.types import FileFlag, GridData, LineData, PointData, ScatterData

from frequency_matching_rain03_plugin_util import describe_task_io


def process_one_lead(date_time, predict_valid, text2, text3, text4, configure_data, sd_sta_info, gd_mask, log):
    """一个起报时刻、一个预报时效的频率匹配订正。"""
    num2 = 3
    missing_logged = 0
    task_desc = StringProcess.date_replace("YYYYMMDDHH_VVV", date_time, predict_valid)
    task_start_time = time.time()
    try:
        io_info = describe_task_io(text2, text4, date_time, predict_valid)
        path2 = io_info["out_m3"]
        path3 = io_info["out_m4"]
        path4 = io_info["model_path"] or io_info["model_raw"]

        if io_info["output_exists"] or io_info["model_missing"]:
            if io_info["output_exists"]:
                log.write_info(f"[SKIP] {task_desc}: output files already exist", 0)
            else:
                missing_logged += 1
                log.write_info(
                    f"[SKIP] {task_desc}: model input not found: {io_info['model_raw']}",
                    1 if missing_logged <= 3 else 0)
            return "skip"

        log.write_info(f"[START] {task_desc}", 1)

        print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        print(StringProcess.date_replace(
            "Process Model Time Is: YYYYMMDDHH_VVV", date_time, predict_valid))
        print("+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
        print("Read the Currect ModelData...")

        dt_input = date_time
        text6 = io_info["model_path"]
        print("Current Model Data: " + text6)
        log.write_info(f"Current model: {text6}", 0)

        gd_current_model = None
        try:
            gd_current_model = GridData(text6)
            log.write_info(f"Model grid: {gd_current_model.xn}x{gd_current_model.yn}", 0)
        except Exception as ex:
            log.write_error(
                f"[FAIL] {task_desc}: cannot read model data {text6}\n"
                f"{traceback.format_exc()}", 1)
            return "fail"

        gd_current_model = gd_current_model.mesh_val(
            configure_data.large_lon_left, configure_data.large_lon_right,
            configure_data.large_lat_bottom, configure_data.large_lat_top,
            configure_data.dlon, configure_data.dlat)
        log.write_info(
            f"Current model after mesh: max={gd_current_model.max_value():.3f} "
            f"n>=10={int((gd_current_model.val >= 10).sum())} "
            f"n>=25={int((gd_current_model.val >= 25).sum())} "
            f"n>=50={int((gd_current_model.val >= 50).sum())}", 0)

        print("Read the History ModelData...")
        num6 = 15  # 同期窗半径（天）
        num7 = 4   # 回溯年数（当年 + 往 3 年）
        ltgd_model_raw = []
        ltsd_fact = []

        hist_found = 0
        hist_missing = 0
        hist_bad = 0

        for j in range(num7):
            date_time2 = date_time
            date_time3 = date_time
            if j == 0:
                date_time2 = date_time - timedelta(days=365 * j) - timedelta(days=num6)
                date_time3 = date_time - timedelta(days=365 * j) - timedelta(days=1)
            else:
                date_time2 = date_time - timedelta(days=365 * j) - timedelta(days=num6)
                date_time3 = date_time - timedelta(days=365 * j) + timedelta(days=num6)

            date_time4 = date_time2
            while date_time4 <= date_time3:
                dt_input2 = date_time4 + timedelta(hours=predict_valid)
                text7_raw, text7 = find_grid_file(text2, date_time4, predict_valid)
                text8_raw, text8 = find_sta_file(text3, dt_input2, 0)

                if text7 and text8:
                    if date_time4 == date_time2 or date_time4 == date_time3:
                        print("dtModel: " + text7)
                        print("dtFact: " + text8)
                    try:
                        grid_data = GridData(text7)
                        grid_data = grid_data.mesh_val(
                            configure_data.large_lon_left, configure_data.large_lon_right,
                            configure_data.large_lat_bottom, configure_data.large_lat_top,
                            configure_data.dlon, configure_data.dlat)
                        scatter_data = sd_sta_info.copy_scatter_data()
                        scatter_data.read_val_from_micaps3(text8)
                        scatter_data.clear_to_num_greater_than(0.0, 500.0)
                        scatter_data.clear_to_num_less_than(0.0, 0.0)
                        ltgd_model_raw.append(grid_data)
                        ltsd_fact.append(scatter_data)
                        hist_found += 1
                    except Exception:
                        print("bad dtModel: " + text7)
                        print("bad dtFact: " + text8)
                        log.write_error(
                            f"[BAD_DATA] {task_desc}: year={j}, date={date_time4.strftime('%Y%m%d')}\n"
                            f"  dtModel={text7}\n  dtFact={text8}\n"
                            f"  {traceback.format_exc()}", 0)
                        hist_bad += 1
                else:
                    missing_files = []
                    if text7 is None:
                        missing_files.append(f"model={text7_raw}")
                        hist_missing += 1
                    if text8 is None:
                        missing_files.append(f"fact={text8_raw}")
                        hist_missing += 1
                    if missing_files:
                        log.write_info(
                            f"[MISSING] {task_desc}: year={j}, date={date_time4.strftime('%Y%m%d')} | "
                            f"{', '.join(missing_files)}", 0)
                    if date_time4 == date_time2 or date_time4 == date_time3:
                        print("lack dtModel: " + (text7 or text7_raw))
                        print("lack dtFact: " + (text8 or text8_raw))

                date_time4 = date_time4 + timedelta(days=1)

        fact_max = max((sd.max_value() for sd in ltsd_fact), default=0.0)
        log.write_info(
            f"History data for {task_desc}: found={hist_found}, missing={hist_missing}, "
            f"bad={hist_bad}, fact_max={fact_max:.3f}", 0)

        dy_n_used = len(ltgd_model_raw)
        if dy_n_used <= 0:
            log.write_error(f"[FAIL] {task_desc}: no history data used! (found=0)", 1)
            return "fail"

        gd_train_model = [None] * dy_n_used
        gd_train_model_smooth = [None] * dy_n_used
        sd_train_fact = [None] * dy_n_used
        print("dyused: " + str(dy_n_used))

        smooth_num = 30  # 历史场 9 点平滑次数
        # 并行化历史成员处理 (匹配C# Parallel.For, scipy/numpy操作会释放GIL)
        def _process_history_member(n):
            try:
                m = ltgd_model_raw[n].copy_grid_data()
                ms = ltgd_model_raw[n].copy_grid_data()
                ms.smooth9(smooth_num)
                f = ltsd_fact[n].copy_scatter_data()
                return n, m, ms, f, None
            except Exception as e:
                return n, None, None, None, traceback.format_exc()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(_process_history_member, n) for n in range(dy_n_used)]
            for future in futures:
                n, m, ms, f, err = future.result()
                if err is not None:
                    log.write_error(
                        f"[WARN] {task_desc}: history member {n} processing failed\n{err}", 0)
                    gd_train_model[n] = ltgd_model_raw[n].copy_grid_data()
                    gd_train_model_smooth[n] = ltgd_model_raw[n].copy_grid_data()
                    sd_train_fact[n] = ltsd_fact[n].copy_scatter_data()
                else:
                    gd_train_model[n] = m
                    gd_train_model_smooth[n] = ms
                    sd_train_fact[n] = f

        gd_current_model_smooth = gd_current_model.copy_grid_data()

        fact_level = [0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0,
                      30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 500.0]
        similar_level = [25.0, 50.0]  # TS+Bias 量级

        scatter_data2 = None

        if predict_valid <= 0:
            # 细粒度分块：将配置区域按约5°切分
            _lon_edges = np.arange(
                configure_data.center_lon_left,
                configure_data.center_lon_right + 0.001, 5.0).tolist()
            _lat_edges = np.arange(
                configure_data.center_lat_bottom,
                configure_data.center_lat_top + 0.001, 5.0).tolist()
            center_lon_left = _lon_edges[:-1]
            center_lon_right = _lon_edges[1:]
            center_lat_bottom = _lat_edges[:-1]
            center_lat_top = _lat_edges[1:]
        else:
            center_lon_left = [configure_data.center_lon_left]
            center_lon_right = [configure_data.center_lon_right]
            center_lat_bottom = [configure_data.center_lat_bottom]
            center_lat_top = [configure_data.center_lat_top]

        num8 = configure_data.lonlat_ext
        large_lon_left = [cl - num8 for cl in center_lon_left]
        large_lon_right = [cr + num8 for cr in center_lon_right]
        large_lat_bottom = [cb - num8 for cb in center_lat_bottom]
        large_lat_top = [ct + num8 for ct in center_lat_top]

        dlon = configure_data.dlon
        dlat = configure_data.dlat

        sd_correct_model = {}
        sub_region_count = 0

        # Precompute the mask meshed to the large region (same for all sub-regions)
        gd_mask_large = gd_mask.copy_grid_data()
        gd_mask_large = gd_mask_large.mesh_val(
            configure_data.large_lon_left, configure_data.large_lon_right,
            configure_data.large_lat_bottom, configure_data.large_lat_top,
            configure_data.dlon, configure_data.dlat)

        for jy in range(len(center_lat_bottom)):
            for ix in range(len(center_lon_left)):
                db_lon2 = [center_lon_left[ix], center_lon_right[ix],
                           center_lon_right[ix], center_lon_left[ix]]
                db_lat2 = [center_lat_bottom[jy], center_lat_bottom[jy],
                           center_lat_top[jy], center_lat_top[jy]]
                scatter_data7 = sd_sta_info.frame_by_line(LineData(db_lon2, db_lat2))

                db_lon3 = [large_lon_left[ix], large_lon_right[ix],
                           large_lon_right[ix], large_lon_left[ix]]
                db_lat3 = [large_lat_bottom[jy], large_lat_bottom[jy],
                           large_lat_top[jy], large_lat_top[jy]]
                sd_sta_info_train = sd_sta_info.frame_by_line(LineData(db_lon3, db_lat3))

                if scatter_data7.length > 0:
                    print(f"jy: {jy} ix: {ix}")
                    sub_region_count += 1

                    try:
                        arr = [None] * dy_n_used
                        for k in range(dy_n_used):
                            arr[k] = gd_train_model_smooth[k].copy_grid_data()
                            arr[k].mask_val(gd_mask_large, 0.0)
                            arr[k] = arr[k].mesh_val(
                                large_lon_left[ix], large_lon_right[ix],
                                large_lat_bottom[jy], large_lat_top[jy],
                                5.0 * dlon, 5.0 * dlat)

                        grid_data5 = gd_current_model_smooth.copy_grid_data()
                        grid_data5.mask_val(gd_mask_large, 0.0)
                        grid_data5 = grid_data5.mesh_val(
                            large_lon_left[ix], large_lon_right[ix],
                            large_lat_bottom[jy], large_lat_top[jy],
                            5.0 * dlon, 5.0 * dlat)

                        # 粗网格上按 TS+Bias 排序历史个例
                        index = Ensemble.get_similarity_index_by_ts_and_bias(
                            arr, grid_data5, dy_n_used, similar_level)

                        num18 = 0
                        num19 = 0.0
                        num20 = 2.4  # 评分累加截断
                        for l in range(len(index[0])):
                            num19 += index[1][l]
                            num18 += 1
                            if num19 > num20:
                                break

                        num21 = min(20, num18)
                        num22 = max(int(0.5 * dy_n_used), num18)

                        gd_sentive_model = [None] * num22
                        sd_sentive_model = [None] * num22
                        sd_sentive_fact = [None] * num22

                        for n in range(num22):
                            gd_sentive_model[n] = gd_train_model_smooth[int(index[0][n])].mesh_val(
                                large_lon_left[ix], large_lon_right[ix],
                                large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                            sd_sentive_model[n] = sd_sta_info_train.copy_scatter_data()
                            sd_sentive_model[n].bilinear_interpolation_from_grid_data(
                                gd_sentive_model[n])
                            sd_sentive_fact[n] = sd_sta_info_train.copy_scatter_data()
                            sd_sentive_fact[n].read_from_sactter_data(
                                sd_train_fact[int(index[0][n])])

                        # 相似个例站点场建分位映射（两端各丢 5 个样本）
                        used_model_level_and_extend2 = FrequencyMatch.get_used_model_level_and_extend(
                            sd_sentive_model, sd_sentive_fact, fact_level, 5)
                        log.write_info(
                            f"Subregion FM levels={len(used_model_level_and_extend2[0])} "
                            f"model={used_model_level_and_extend2[0]} "
                            f"fact={used_model_level_and_extend2[1]}", 0)

                        grid_data6 = gd_current_model_smooth.mesh_val(
                            large_lon_left[ix], large_lon_right[ix],
                            large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                        grid_data7 = grid_data6.copy_grid_data()
                        if len(used_model_level_and_extend2[0]) < 2:
                            grid_data7 = gd_current_model.mesh_val(
                                large_lon_left[ix], large_lon_right[ix],
                                large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                        else:
                            grid_data7 = FrequencyMatch.correct_model_data(
                                grid_data6, used_model_level_and_extend2[1],
                                used_model_level_and_extend2[0])

                        # 仅时效<=0：光流反演 + 半拉格朗日（默认 3–252 不进入）
                        if predict_valid <= 0:
                            array2 = [
                                GridData(large_lon_left[ix], large_lon_right[ix],
                                         large_lat_bottom[jy], large_lat_top[jy], dlon, dlat),
                                GridData(large_lon_left[ix], large_lon_right[ix],
                                         large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                            ]
                            num22_opt = num21
                            array3 = [None] * num22_opt
                            array4 = [None] * num22_opt

                            for num23 in range(num22_opt):
                                array3[num23] = gd_train_model[int(index[0][num23])].copy_grid_data()
                                sd_input_data = sd_train_fact[int(index[0][num23])].copy_scatter_data()
                                array4[num23] = SpatialAnalisis.gress_man_interpolation_for_rain(
                                    sd_input_data, array3[num23],
                                    [1.0, 0.8, 0.6, 0.4])
                                array3[num23].smooth9(smooth_num)
                                array3[num23] = array3[num23].mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                                array4[num23].smooth9(smooth_num)
                                array4[num23] = array4[num23].mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                                used_model_level_and_extend3 = FrequencyMatch.get_used_model_level_and_extend(
                                    [array3[num23]], [array4[num23]], fact_level)
                                if len(used_model_level_and_extend3[0]) >= 2:
                                    array3[num23] = FrequencyMatch.correct_model_data(
                                        array3[num23], used_model_level_and_extend3[1],
                                        used_model_level_and_extend3[0])

                                array4[num23] = array4[num23].mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy],
                                    1.0 * dlon, 1.0 * dlat)
                                array3[num23] = array3[num23].mesh_val(
                                    large_lon_left[ix], large_lon_right[ix],
                                    large_lat_bottom[jy], large_lat_top[jy],
                                    1.0 * dlon, 1.0 * dlat)

                            array2[0] = array3[0].copy_grid_data()
                            array2[1] = array3[0].copy_grid_data()
                            array2[0].clear_to_num(0.0)
                            array2[1].clear_to_num(0.0)

                            min_window = [[5.0, 5.0]]
                            OpticalFlow.get_wind_from_optical_flow(
                                array3, array4, min_window, array2, 25.0, 0.1, 50)

                            array2[0] = array2[0].mesh_val(
                                large_lon_left[ix], large_lon_right[ix],
                                large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)
                            array2[1] = array2[1].mesh_val(
                                large_lon_left[ix], large_lon_right[ix],
                                large_lat_bottom[jy], large_lat_top[jy], dlon, dlat)

                            grid_data8 = grid_data7.copy_grid_data()
                            min_val = 10.0
                            max_val = 25.0
                            grid_data8.standardize_by_max_min(min_val, max_val)
                            gd_u_wnd = array2[0].multi_val_form_new_grid_data(grid_data8)
                            gd_v_wnd = array2[1].multi_val_form_new_grid_data(grid_data8)

                            grid_data7 = RainExtrapolation.simple_semi_lagrangian_in_angle(
                                gd_u_wnd, gd_v_wnd, grid_data7, 1.0)

                        sd_correct_model[(ix, jy)] = scatter_data7.copy_scatter_data()
                        sd_correct_model[(ix, jy)].bilinear_interpolation_from_grid_data(
                            grid_data7)
                        sd_correct_model[(ix, jy)].clear_to_num_less_than(0.0, 0.01)

                    except Exception as ex_sub:
                        log.write_error(
                            f"[WARN] {task_desc}: sub-region (ix={ix}, jy={jy}) failed\n"
                            f"  {traceback.format_exc()}", 0)

        log.write_info(
            f"Sub-regions processed: {sub_region_count}/{len(center_lat_bottom) * len(center_lon_left)}", 0)

        db_lon = [center_lon_left[0],
                  center_lon_right[-1],
                  center_lon_right[-1],
                  center_lon_left[0]]
        db_lat = [center_lat_bottom[0],
                  center_lat_bottom[0],
                  center_lat_top[-1],
                  center_lat_top[-1]]
        scatter_data2 = sd_sta_info.frame_by_line(LineData(db_lon, db_lat))

        for jy in range(len(center_lat_bottom)):
            for ix in range(len(center_lon_left)):
                if (ix, jy) in sd_correct_model:
                    scatter_data2.read_from_sactter_data(sd_correct_model[(ix, jy)])

        # 输出站点数据（meb：sta_data → write_stadata_to_micaps3）
        scatter_data3 = scatter_data2.copy_scatter_data()
        text9 = expand_data_path(text4 + ".m3", date_time, predict_valid)
        print(text9)
        scatter_data3.clear_to_num_less_than(0.0, 0.01)
        try:
            scatter_data3.writer_to_micaps3(
                text9, dt_input=date_time, i_valid=predict_valid)
            sta_max = scatter_data3.max_value() if scatter_data3.length else 0.0
            log.write_info(
                f"Output station data: {text9} max={sta_max:.3f} "
                f"nsta={scatter_data3.length}", 0)
        except Exception as e:
            log.write_error(
                f"[FAIL] {task_desc}: cannot write .m3 file {text9}\n"
                f"  {traceback.format_exc()}", 1)
            return "fail"

        # .m3raw 输出暂时关闭 — 原始模式插值到站点的数据，非核心产品
        # scatter_data4 = scatter_data3.copy_scatter_data()
        # scatter_data4.bilinear_interpolation_from_grid_data(gd_current_model)
        # str_header = StringProcess.date_replace(
        #     "diamond 3 YYYY年MM月DD日HH时VVV时效" + f"{num2:03d}" +
        #     "小时累积降水 00 01 04 08  -1 0 1 0 0",
        #     date_time, predict_valid)
        # text9 = StringProcess.date_replace(text4 + ".m3raw", date_time, predict_valid)
        # print(text9)
        # scatter_data4.clear_to_num_less_than(0.0, 0.01)
        # scatter_data4.writer_to_micaps3(text9, str_header)
        # log.write_info(f"Output raw station data: {text9}", 0)

        print("Output The Correct GridData...")
        grid_data2 = gd_current_model.mesh_val(
            configure_data.center_lon_left, configure_data.center_lon_right,
            configure_data.center_lat_bottom, configure_data.center_lat_top,
            configure_data.dlon, configure_data.dlat)
        gd_mask_mesh = gd_mask.mesh_val(
            configure_data.center_lon_left, configure_data.center_lon_right,
            configure_data.center_lat_bottom, configure_data.center_lat_top,
            configure_data.dlon, configure_data.dlat)

        # 掩膜<0 视为境外：每 5 点抽背景当伪站
        lst_points = []
        for num15 in range(0, gd_mask_mesh.yn, 5):
            for num16 in range(0, gd_mask_mesh.xn, 5):
                if gd_mask_mesh.val[num15, num16] < 0.0:
                    lst_points.append(PointData(
                        grid_data2.lon[num16], grid_data2.lat[num15],
                        grid_data2.val[num15, num16]))

        for num17 in range(scatter_data3.length):
            lst_points.append(scatter_data3.sta_data[num17].copy_point_data())

        scatter_data5 = ScatterData(lst_points)
        print("sta num for cressman: " + str(len(scatter_data5.sta_data)))
        log.write_info(f"Cressman input points: {len(scatter_data5.sta_data)}", 0)

        # 影响半径按经距的 8/6/4/2 倍逐步订正
        grid_data3 = SpatialAnalisis.gress_man_interpolation_for_rain(
            scatter_data5, grid_data2,
            [8.0 * configure_data.dlon, 6.0 * configure_data.dlon,
             4.0 * configure_data.dlon, 2.0 * configure_data.dlon])
        grid_data3.smooth9(10)

        scatter_data6 = scatter_data3.copy_scatter_data()
        scatter_data6.bilinear_interpolation_from_grid_data(grid_data3)

        fact_level2 = [0.01, 0.1, 0.5, 1.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0,
                       25.0, 30.0, 40.0, 50.0, 75.0, 100.0, 150.0, 200.0, 250.0]

        used_model_level_and_extend = FrequencyMatch.get_used_model_level_and_extend(
            [scatter_data6], [scatter_data3], fact_level2)

        if len(used_model_level_and_extend[0]) < 2:
            grid_data3 = grid_data2.copy_grid_data()
            log.write_info("Frequency match levels < 2, using original model data", 0)
        else:
            grid_data3 = FrequencyMatch.correct_model_data(
                grid_data3, used_model_level_and_extend[1],
                used_model_level_and_extend[0])
            log.write_info(f"Frequency match applied: {len(used_model_level_and_extend[0])} levels", 0)

        grid_data3.clear_to_num_less_than(0.0, 0.01)

        # meb：grid_data → write_griddata_to_micaps4 / write_griddata_to_nc
        text10 = expand_data_path(text4, date_time, predict_valid)
        m4_title = StringProcess.date_replace(
            f"YYYYMMDDHH_VVV时效{num2:03d}小时降水预报场",
            date_time, predict_valid)

        # .cybin 和 .m4raw 输出暂时关闭
        # grid_data3.write_val_to_cybin(text10 + ".cybin")
        try:
            grid_data3.write_val_to_micaps4(
                text10 + ".m4", title=m4_title,
                dt_input=date_time, i_valid=predict_valid)
            log.write_info(f"Output grid data: {text10}.m4", 0)
        except Exception as e:
            log.write_error(
                f"[FAIL] {task_desc}: cannot write .m4 file {text10}.m4\n"
                f"  {traceback.format_exc()}", 1)
        # 同时保存 NC 格式
        try:
            grid_data3.write_val_to_nc(text10 + ".nc", dt_input=dt_input, i_valid=predict_valid)
            log.write_info(f"Output grid data: {text10}.nc", 0)
        except Exception as e:
            log.write_error(
                f"[FAIL] {task_desc}: cannot write .nc file {text10}.nc\n"
                f"  {traceback.format_exc()}", 1)

        task_elapsed = time.time() - task_start_time
        log.write_info(f"[DONE] {task_desc}: completed in {task_elapsed:.1f}s", 1)
        return "success"

    except Exception as ex2:
        task_elapsed = time.time() - task_start_time
        task_desc = StringProcess.date_replace(
            "YYYYMMDDHH_VVV", date_time, predict_valid)
        log.write_error(
            f"[FAIL] {task_desc}: unhandled exception after {task_elapsed:.1f}s\n"
            f"  {traceback.format_exc()}", 1)

        return "fail"



class FrequencyMatchingRain03Plugin:
    """一个起报 × 一个时效的频率匹配订正。"""

    def __init__(
        self,
        model_template,
        fact_template,
        output_template,
        configure_data,
        sd_sta_info,
        gd_mask,
        log,
    ):
        self.model_template = model_template
        self.fact_template = fact_template
        self.output_template = output_template
        self.configure_data = configure_data
        self.sd_sta_info = sd_sta_info
        self.gd_mask = gd_mask
        self.log = log

    def process(self, date_time, predict_valid):
        """读入已在 CLI 备好；本方法跑核心算法并写出产品。返回 skip/fail/success。"""
        return process_one_lead(
            date_time,
            predict_valid,
            self.model_template,
            self.fact_template,
            self.output_template,
            self.configure_data,
            self.sd_sta_info,
            self.gd_mask,
            self.log,
        )
