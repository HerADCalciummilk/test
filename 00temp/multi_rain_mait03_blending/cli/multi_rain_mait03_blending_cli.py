# -*- coding: utf-8 -*-
"""3 小时气象预报集成。

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

from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool
from mait_3_plugin import (
    AnalysisTsWeightProcess,
    StationDataInterp2GridDataProcess,
    DataFlgProcess,
)
from mait_3_plugin_util import (
    write_beta,
    _data_write_to_micaps3,
    get_now_beta_file_path,
    get_his_beta_file_path,
    read_his_beta,
    write_grid_to_micaps4,
    _prepare,
    _analysis_para_ini,
    _analysis_background_ini,
    _read_history_source_micaps3,
    _read_now_source_micaps3_micaps4,
    read_grid_mask,
)

_DEFAULT_VALID = list(range(3, 253, 3))
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


def _process(
    time_input,
    *,
    para_path,
    beta_path,
    background_path,
    is_obs_bjt,
    is_interp,
    clip_coords,
    predict_valid_list,
    log_file,
    station_info,
    mask_dat,
):
    """执行一个起报下全部预报时效的集成。"""
    if not time_input or not para_path or not station_info or not mask_dat:
        return
    try:
        para_file = _abs_path(para_path)
        beta_file = _abs_path(beta_path) if beta_path else beta_path
        background_file = _abs_path(background_path) if background_path else background_path
        log_path = _abs_path(log_file) if log_file else log_file
        station_file = _abs_path(station_info)
        mask_file = _abs_path(mask_dat)
        area_scale = 0.5
        predict_type = 3
        if not predict_valid_list:
            return

        for predict_valid in predict_valid_list:
            simple_log, dt_now, sd_sta_info = _prepare(time_input, log_path, station_file)
            ini_tuple = _analysis_para_ini(para_file, simple_log)
            if not ini_tuple:
                print("[SKIP] para invalid or missing: %s" % para_file, flush=True)
                return
            model_num, model_name, model_path, fact_path, output_sample_path = ini_tuple
            background_templates = _analysis_background_ini(background_file)

            hist = _read_history_source_micaps3(
                predict_valid, dt_now, model_num, sd_sta_info, fact_path, simple_log,
                model_path, is_obs_bjt)
            if hist is None:
                print("[SKIP] valid=%03d: fact missing, continue next lead time" % predict_valid, flush=True)
                continue
            (
                sta_before_flg, sta_current_flg1, sd_current_model, sd_before_model,
                sd_fact, md_current_yr, md_current_mo, md_current_dy,
                md_current_hr_utc, dt_model_current,
            ) = hist

            sta_current_flg2, gd_back_ground, grid_base = _read_now_source_micaps3_micaps4(
                model_num, model_path, dt_model_current, predict_valid, model_name,
                sta_current_flg1, simple_log, sd_sta_info, sd_current_model,
                md_current_yr, md_current_mo, md_current_dy, md_current_hr_utc,
                background_templates=background_templates)

            before_total_flg, current_total_flg, sta_current_flg = DataFlgProcess(
                model_num, sta_before_flg, sta_current_flg2, simple_log).process()
            if before_total_flg == 0.0:
                print("All Before Data Is Not Exist!\n", flush=True)
                continue
            if current_total_flg == 0.0:
                print("All Current Data Is Not Exist!\n", flush=True)
                continue

            obeta_file_path_list = get_now_beta_file_path(beta_file, grid_base)
            ibeta_file_path_list, iflag_list = get_his_beta_file_path(beta_file, grid_base)
            score_before_list, iflag_list = read_his_beta(
                ibeta_file_path_list, iflag_list, model_num, model_name, grid_base)

            analysis_ts = AnalysisTsWeightProcess(
                grid_base, area_scale, model_num,
                sd_before_model, sd_current_model, sd_sta_info, sd_fact,
                sta_before_flg, model_name, sta_current_flg,
                iflag_list, score_before_list)
            sd_output, score_last = analysis_ts.process()
            write_beta(obeta_file_path_list[0][0][0], model_num, model_name, score_last)
            _data_write_to_micaps3(predict_type, output_sample_path, sd_output, grid_base)

            gd_mask_val, gd_mask_xn, gd_mask_yn = read_grid_mask(mask_file, grid_base)
            gd_final_output = StationDataInterp2GridDataProcess(
                gd_mask_val, gd_mask_xn, gd_mask_yn, grid_base, gd_back_ground, sd_output).process()
            write_grid_to_micaps4(
                gd_final_output, output_sample_path, predict_type,
                clip_coords, grid_base, is_interp)
    except Exception as exc:
        print("集成失败 time_input=%s: %s" % (time_input, exc))


@merge_params()
def process(
    time_inputs: list = None,
    pro_count: int = 1,
    *,
    predict_valid_list: List[int] = None,
    para_path: str = "resource/para_3.ini",
    beta_path: str = "beta_3h/YYYYMMDDHH/%02d_%02d_TTT.info",
    background_path: str = "resource/para_3_background.ini",
    is_obs_bjt: bool = True,
    is_interp: bool = False,
    clip_coords: List[float] = None,
    log_file: str = "log/YYYYMMDD.txt",
    station_info: str = "resource/station_info.txt",
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
        "background_path": background_path,
        "is_obs_bjt": is_obs_bjt,
        "is_interp": is_interp,
        "clip_coords": clip_coords,
        "predict_valid_list": predict_valid_list,
        "log_file": log_file,
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
