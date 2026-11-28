# -*- coding: utf-8 -*-
"""1 小时气象预报集成。

一条任务是一个起报 ``time_input``。该起报下的全部时效在这一条任务里循环。
``pro_count`` 大于 1 时，``process`` 把 ``_process`` 交给进程池。
"""
import datetime
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
from mait_1_plugin import AnalysisTsWeightProcess, StationDataInterp2GridDataProcess, DataFlgProcess
from mait_1_plugin_util import (
    _read_history_source_micaps3,
    _read_mait_st_like_score_samples,
    _read_now_source_micaps3_nc,
    _analysis_background_ini,
)
from utils.util_new import (
    read_grid_mask,
    _prepare,
    _analysis_para_ini,
    _data_write_to_micaps3,
    write_grid_to_micaps4,
)

_DEFAULT_VALID = list(range(1, 49))
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
    log_file,
    background_ini,
    station_info,
):
    """读参数文件、站点表和背景路径，组装本次 RunContext。"""
    simple_log, dt_now, sd_sta_info = _prepare(time_input, log_file, station_info)
    ini_tuple = _analysis_para_ini(para_path, simple_log)
    if not ini_tuple:
        return None, simple_log
    model_name, model_path, fact_path, output_sample_path = ini_tuple

    background_templates = _analysis_background_ini(background_ini)
    if not background_templates:
        simple_log.error("背景格点配置文件不存在或为空: %s", background_ini)
        return None, simple_log
    missing = [name for name in model_name if name not in background_templates]
    if missing:
        simple_log.error("背景配置缺少模式键（须与 para 文件一致）: %s", ", ".join(missing))
        return None, simple_log

    ctx = build_run_context(
        beta_path_template=beta_path,
        is_obs_bjt=is_obs_bjt,
        clip_coords=clip_coords,
        split_lat=split_lat,
        split_lon=split_lon,
        dt_now=dt_now,
        sd_sta_info=sd_sta_info,
        simple_log=simple_log,
        model_name=model_name,
        model_path=model_path,
        fact_path=fact_path,
        output_sample_path=output_sample_path,
        background_templates=background_templates,
        area_scale=0.5,
        predict_type=1,
    )
    return ctx, simple_log


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
    mask_dat,
):
    """执行一个起报下全部预报时效的集成。"""
    if not time_input or not para_path or not station_info or not mask_dat:
        return
    try:
        para_file = _abs_path(para_path)
        log_path = _abs_path(log_file) if log_file else log_file
        station_file = _abs_path(station_info)
        mask_file = _abs_path(mask_dat)
        ctx, simple_log = _setup_context(
            time_input,
            para_file,
            _abs_path(beta_path) if beta_path else beta_path,
            is_obs_bjt,
            clip_coords,
            split_lat,
            split_lon,
            log_path,
            _abs_path(background_ini) if background_ini else background_ini,
            station_file,
        )
        if ctx is None:
            if simple_log is not None:
                print("RunContext 初始化失败，详见日志:", log_path)
            return

        model_name = list(ctx.models.model_name)
        if not predict_valid_list:
            return

        for predict_valid in predict_valid_list:
            sta_before_flg, sta_current_flg1, sd_current_model, sd_before_model, sd_fact, md_current_datetime, dt_model_current = (
                _read_history_source_micaps3(predict_valid, ctx))
            before_model_series, before_model_flag, before_fact_series, before_fact_flag, front_model, front_model_flag, front_fact = (
                _read_mait_st_like_score_samples(predict_valid, ctx))
            if before_model_flag is not None:
                for i_model in range(len(ctx.paths.model_path)):
                    if np.any(before_model_flag[i_model, :] == 1.0):
                        sta_before_flg[i_model] = 1.0

            dt_search_base = ctx.dt_search_base()
            sta_current_flg2, gd_back_ground, grid_base, _ = _read_now_source_micaps3_nc(
                dt_model_current, predict_valid, sta_current_flg1, sd_current_model,
                md_current_datetime, ctx, dt_search_base=dt_search_base)
            grid_base.gtime = [dt_search_base]
            grid_base.dtimes = [predict_valid]

            _, current_total_flg, sta_current_flg = DataFlgProcess(
                sta_before_flg, sta_current_flg2, ctx).process()
            if current_total_flg == 0.0:
                continue

            iflag_list = [[[0 for _ in range(ctx.grid.split_lon)] for _ in range(ctx.grid.split_lat)]]
            score_before_list = [[[[0.0 for _ in model_name] for _ in range(ctx.grid.split_lon)] for _ in range(ctx.grid.split_lat)]]
            analysis_ts = AnalysisTsWeightProcess(
                grid_base, sd_before_model, sd_current_model, sd_fact,
                sta_before_flg, sta_current_flg, iflag_list, score_before_list, ctx,
                before_model_series=before_model_series,
                before_model_flag=before_model_flag,
                before_fact_series=before_fact_series,
                before_fact_flag=before_fact_flag,
                front_model=front_model,
                front_model_flag=front_model_flag,
                front_fact=front_fact,
            )
            sd_output, _score_last = analysis_ts.process()

            sd_outputs = []
            for idx in range(len(sd_output[0])):
                for jdx in range(len(sd_output[0][idx])):
                    sd_outputs.append(sd_output[0][idx][jdx])
            __sd_output = pd.concat(sd_outputs, ignore_index=True)
            if "id" in __sd_output.columns:
                __sd_output = __sd_output.drop_duplicates(subset=["id"], keep="last").reset_index(drop=True)
            if "data0" in __sd_output.columns:
                __sd_output["data0"] = __sd_output["data0"] * 1.2

            _data_write_to_micaps3(__sd_output, grid_base, ctx)
            gd_mask_val, gd_mask_xn, gd_mask_yn = read_grid_mask(mask_file, grid_base)
            gd_final_output = StationDataInterp2GridDataProcess(
                gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground, __sd_output).process()
            write_grid_to_micaps4(gd_final_output, grid_base, ctx)
    except Exception as exc:
        print("集成失败 time_input=%s: %s" % (time_input, exc))


@merge_params()
def process(
    time_inputs: list = None,
    pro_count: int = 1,
    *,
    predict_valid_list: List[int] = None,
    para_path: str = "resource/para_1.ini",
    beta_path: str = "beta_1h/YYYYMMDDHH",
    is_obs_bjt: bool = True,
    clip_coords: List[float] = None,
    split_lat: int = 1,
    split_lon: int = 1,
    log_file: str = "log/YYYYMMDD.txt",
    background_ini: str = "resource/para_1_background.ini",
    station_info: str = "resource/sta.info",
    mask_dat: str = "resource/mask010.dat",
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
        "mask_dat": mask_dat,
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
