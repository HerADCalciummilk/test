# -*- coding: utf-8 -*-
"""24 小时气象预报集成。

一条任务是一个起报 ``time_input``。该起报下的全部时效在这一条任务里循环。
``pro_count`` 大于 1 时，``process`` 把 ``_process`` 交给进程池。
"""
import datetime
import logging
import os
import sys
from typing import List

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd

from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool
from utils.util_context import build_run_context
from mait_24_plugin import AnalysisTsWeightProcess, StationDataInterp2GridDataProcess
from mait_24_plugin_util import (
    _read_history_source_micaps3,
    _read_now_source_micaps3_micaps4,
    _analysis_background_ini,
)
from utils.util_new import (
    read_grid_mask_nc,
    _prepare,
    _analysis_para_ini,
    init_run_log,
    _data_write_to_micaps3,
    write_grid_to_micaps4,
    get_now_beta_file_path_npy,
    get_his_beta_file_path_npy,
    read_his_beta_npy,
    write_beta_npy,
)

_DEFAULT_VALID = [36, 60, 84, 108, 132, 156, 180, 204, 228, 252]
_DEFAULT_CLIP = [70.0, 140.0, 0.0, 60.0, 0.1, 0.1]


def _abs_path(path):
    """相对路径按本包根目录解析。"""
    path = os.path.expanduser(str(path))
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(_ROOT_DIR, path))


def _as_list(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _setup_context(
    time_input,
    para_path,
    beta_path,
    is_obs_bjt,
    clip_coords,
    split_lat,
    split_lon,
    predict_valid_list,
    log_file,
    background_ini,
    station_info,
):
    """读参数文件、站点表和背景路径，组装本次 RunContext。"""
    log = init_run_log(_abs_path(log_file) if log_file else log_file, time_input=time_input)
    log.info("启动 time_input=%s valid_list=%s", time_input, predict_valid_list)

    try:
        dt_now, sd_sta_info = _prepare(time_input, _abs_path(station_info))
    except Exception as exc:
        log.error("准备阶段失败: %s", exc)
        return None, log

    para_file = _abs_path(para_path)
    ini_tuple = _analysis_para_ini(para_file)
    if not ini_tuple:
        log.error("参数文件不存在或内容错误: %s", para_file)
        return None, log
    model_name, model_path, fact_path, output_sample_path = ini_tuple

    background_file = _abs_path(background_ini) if background_ini else background_ini
    background_templates = _analysis_background_ini(background_file)
    ctx = build_run_context(
        beta_path_template=_abs_path(beta_path) if beta_path else beta_path,
        is_obs_bjt=is_obs_bjt,
        clip_coords=clip_coords,
        split_lat=split_lat,
        split_lon=split_lon,
        dt_now=dt_now,
        sd_sta_info=sd_sta_info,
        model_name=model_name,
        model_path=model_path,
        fact_path=fact_path,
        output_sample_path=output_sample_path,
        background_templates=background_templates,
    )
    return ctx, log


def _process(
    time_input,
    *,
    para_path,
    beta_path,
    is_obs_bjt,
    clip_coords,
    split_lat,
    split_lon,
    predict_valid_list,
    log_file,
    background_ini,
    station_info,
    mask_nc,
):
    """执行一个起报下全部预报时效的集成。"""
    if not time_input or not para_path or not station_info or not mask_nc:
        return
    try:
        ctx, log = _setup_context(
            time_input, para_path, beta_path, is_obs_bjt, clip_coords, split_lat, split_lon,
            predict_valid_list, log_file, background_ini, station_info,
        )
        if ctx is None:
            return

        model_name = list(ctx.models.model_name)
        try:
            gd_mask_val, gd_mask_xn, gd_mask_yn = read_grid_mask_nc(_abs_path(mask_nc))
        except Exception as exc:
            log.error("掩码文件读取失败: %s", exc)
            return

        for predict_valid in predict_valid_list:
            try:
                sta_before_flg, sta_current_flg, sd_current_model, sd_before_model, sd_fact, md_current_datetime, dt_model_current = (
                    _read_history_source_micaps3(predict_valid, ctx))
                sta_current_flg, gd_back_ground, grid_base = _read_now_source_micaps3_micaps4(
                    dt_model_current, predict_valid, sta_current_flg, sd_current_model,
                    md_current_datetime, ctx)
            except Exception as exc:
                log.error("读取资料失败 valid=%sh: %s", predict_valid, exc)
                return

            if not np.any(sta_before_flg):
                log.error("历史模式数据均不存在 valid=%sh", predict_valid)
                return
            if not np.any(sta_current_flg):
                log.error("当前模式数据均不存在 valid=%sh", predict_valid)
                return

            obeta_file_path_list = get_now_beta_file_path_npy(grid_base, ctx)
            ibeta_file_path_list, iflag_list = get_his_beta_file_path_npy(grid_base, ctx)
            score_before_list, iflag_list = read_his_beta_npy(
                ibeta_file_path_list, iflag_list, grid_base, ctx)

            analysis_ts = AnalysisTsWeightProcess(
                grid_base, sd_before_model, sd_current_model, sd_fact,
                sta_before_flg, sta_current_flg, iflag_list, score_before_list, ctx)
            sd_output, score_last = analysis_ts.process()

            score_last_np = np.asarray(score_last)
            sd_outputs = []
            for idx, obeta_file_paths in enumerate(obeta_file_path_list[0]):
                for jdx, obeta_file_path in enumerate(obeta_file_paths):
                    write_beta_npy(obeta_file_path, model_name, score_last_np[0][idx][jdx])
                    sd_outputs.append(sd_output[0][idx][jdx])
            __sd_output = pd.concat(sd_outputs, ignore_index=True)

            _data_write_to_micaps3(__sd_output, grid_base, ctx)
            gd_final_output = StationDataInterp2GridDataProcess(
                gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground, __sd_output).process()
            write_grid_to_micaps4(gd_final_output, grid_base, ctx)
            log.info("时效 %sh 处理完成", predict_valid)

        log.info("全部时效处理完成 time_input=%s", time_input)
    except Exception as exc:
        logging.getLogger("mait_24h").error("集成失败 time_input=%s: %s", time_input, exc)


@merge_params()
def process(
    time_inputs: list = None,
    pro_count: int = 1,
    *,
    predict_valid_list: List[int] = None,
    para_path: str = "resource/para_24.ini",
    beta_path: str = "resource/YYYYMMDDHH",
    is_obs_bjt: bool = True,
    clip_coords: List[float] = None,
    split_lat: int = 1,
    split_lon: int = 1,
    log_file: str = "log/YYYYMMDD.txt",
    background_ini: str = "resource/para_24_background.ini",
    station_info: str = "resource/station_info.txt",
    mask_nc: str = "resource/mask010.nc",
    config=None,
):
    """展开全部起报；pro_count 大于 1 时并行调用 _process。"""
    time_inputs = _as_list(time_inputs)
    if not time_inputs:
        raise ValueError("缺少参数: time_inputs（调用参数与配置文件均未提供）")
    predict_valid_list = _as_list(predict_valid_list) or list(_DEFAULT_VALID)
    clip_coords = _as_list(clip_coords) or list(_DEFAULT_CLIP)
    blend_para = {
        "para_path": para_path,
        "beta_path": beta_path,
        "is_obs_bjt": is_obs_bjt,
        "clip_coords": clip_coords,
        "split_lat": split_lat,
        "split_lon": split_lon,
        "predict_valid_list": predict_valid_list,
        "log_file": log_file,
        "background_ini": background_ini,
        "station_info": station_info,
        "mask_nc": mask_nc,
    }
    if pro_count > 1:
        sw_all = datetime.datetime.now()
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=pro_count,
            fixed_params=blend_para,
        ).process({"time_input": time_inputs})
        print(">>> Time elasped: " + str((datetime.datetime.now() - sw_all).total_seconds()))
    else:
        for time_input in time_inputs:
            _process(time_input, **blend_para)
