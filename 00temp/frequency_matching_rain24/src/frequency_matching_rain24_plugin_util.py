# -*- coding: utf-8 -*-
import json
import os
import sys
from datetime import datetime, timedelta

import meteva.base as meb
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SRC_DIR)
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from frequency_matching_rain24_plugin import Lagrangian
from interpolation import GressManInterpolation, mesh_val
from utils.cressman_extrap_reprocess import (
    LagrangianAligned,
    cressman_project_innov,
    project_innov_wrap,
)
from utils.logger import logger
from utils.config import expansion, his_day, his_year, smooth_num
from utils.data_proc import (
    GetNumDown,
    GetNumUp,
    clear_to_num_greater_than,
    clear_to_num_less_than,
    select_by_extend,
    smooth9,
)

_MODE_ALIASES = {
    "original": "original",
    "orig": "original",
    "baseline": "original",
    "legacy": "original",
    "aligned": "aligned",
    "align": "aligned",
    "project": "aligned",
    "reprocess": "aligned",
}


def _normalize_mode(match_mode: str) -> str:
    key = str(match_mode or "aligned").strip().lower().replace("-", "_")
    if key not in _MODE_ALIASES:
        raise ValueError(
            "未知 match_mode=%r，可选: aligned | original" % (match_mode,)
        )
    return _MODE_ALIASES[key]


def _cressman_and_lagrangian(match_mode: str):
    """按 match_mode 选切片 Cressman、格点 Cressman、外推类。

    aligned：项目再处理 ``cressman_project_innov`` / ``project_innov_wrap`` + ``LagrangianAligned``
    original：原版 ``GressManInterpolation`` + ``Lagrangian``
    估 UV 两边都用原版 ``OpticalFlow``。
    """
    mode = _normalize_mode(match_mode)
    if mode == "aligned":
        return cressman_project_innov, project_innov_wrap, LagrangianAligned
    return GressManInterpolation, GressManInterpolation, Lagrangian



def _abs_path(path):
    """相对路径按本包根目录解析。

    兼容旧写法 ``../resource/...``（相对 cli 目录）：统一归到本包 ``resource/``。
    以 ``./`` 开头的仍按当前工作目录解析。
    """
    path = os.path.expanduser(str(path))
    if os.path.isabs(path):
        return os.path.normpath(path)
    norm = path.replace("\\", "/")
    if norm.startswith("../resource/") or norm.startswith("..\\resource\\"):
        path = "resource/" + norm.split("resource/", 1)[-1].lstrip("/\\")
        return os.path.normpath(os.path.join(_ROOT_DIR, path))
    if path.startswith("./"):
        return os.path.normpath(os.path.abspath(path))
    return os.path.normpath(os.path.join(_ROOT_DIR, path))


def _expand_report_times(rpt_times, report_inter):
    """按起报列表和 report_inter 展开起报时间，由近到远。"""
    report_list = list(rpt_times)
    if len(report_list) == 0:
        end_time = datetime.now() - timedelta(hours=datetime.now().hour % report_inter)
        start_time = end_time - timedelta(days=1)
    elif len(report_list) == 1:
        start_time = datetime.strptime(str(report_list[0]), "%Y%m%d%H")
        end_time = start_time
    elif len(report_list) == 2:
        start_time = datetime.strptime(str(report_list[0]), "%Y%m%d%H")
        end_time = datetime.strptime(str(report_list[1]), "%Y%m%d%H")
    else:
        raise ValueError("输入参数有误, 请输入%Y%m%d%H")
    report_times = []
    report_time = end_time
    while report_time >= start_time:
        report_times.append(report_time)
        report_time -= timedelta(hours=report_inter)
    return report_times


def _expand_dtime_list(start_dtime, end_dtime, inter_dtime1, inter_dtime2):
    """按起止时效展开预报时效，60 小时前用 inter_dtime1，其后用 inter_dtime2。"""
    dtime_list = []
    begin_dtime = start_dtime
    while begin_dtime <= end_dtime:
        dtime_list.append(begin_dtime)
        begin_dtime += inter_dtime1 if begin_dtime < 60 else inter_dtime2
    return dtime_list


def _get_obs_time(model_time, dtime, ipt_model, ipt_obs):
    """按模式与实况的时区差，把起报时间和时效换算成实况时间。"""
    if ipt_model == ipt_obs:
        return model_time + timedelta(hours=dtime)
    if ipt_model >= 1 and ipt_obs == 0:
        return model_time + timedelta(hours=dtime) - timedelta(hours=8)
    if ipt_model == 0 and ipt_obs >= 1:
        return model_time + timedelta(hours=dtime) + timedelta(hours=8)
    raise TypeError("输入降水数据时间判断有误")


def _read_grid(path, ipt_type, data_name):
    """按 ipt_type 读取 micaps4 或 nc 格点。"""
    if ipt_type == "m4":
        return meb.read_griddata_from_micaps4(path)
    if ipt_type == "nc":
        return meb.read_griddata_from_nc(path)
    logger.error("%s数据格式有误：%s", data_name, path)
    return None


def _load_dataset(plugin, report_time, dtime, correct_para, match_mode="aligned"):
    """读入一条任务所需数据，供 CLI 第 1 步调用。

    含：plugin 路径、历史模式/实况站、当前模式、掩码、分块范围；
    不跑算法插件。
    """
    mode = _normalize_mode(match_mode)
    parafile = _abs_path(plugin)
    if not os.path.exists(parafile):
        logger.error("缺失配置文件：%s", parafile)
        sys.exit(1)
    with open(parafile, "r", encoding="utf-8") as cfg_file:
        path_config = json.load(cfg_file)
    tp_model = path_config.get("tp_model")
    tp_obs = path_config.get("tp_obs")
    correct_tp_outpath = path_config.get("correct_tp_outpath").format(rpt=report_time, dtime=dtime)
    current_modelpath = tp_model.format(rpt=report_time, dtime=dtime)
    opt_m3 = correct_tp_outpath + ".m3"
    opt_grd = correct_tp_outpath + "." + correct_para["opt_type"]
    if not os.path.exists(current_modelpath):
        logger.error("当前数据缺失")
        return None
    if os.path.exists(opt_m3) and os.path.exists(opt_grd) and correct_para["over_w"] != 1:
        logger.info("本地已存在降水订正产品")
        return None

    slon, elon, slat, elat = [float(v) for v in correct_para["clip_coords"]]
    dataset = {
        "rpt": report_time,
        "dtime": dtime,
        "match_mode": mode,
        "ipt_model": correct_para["ipt_model"],
        "ipt_obs": correct_para["ipt_obs"],
        "ipt_type": correct_para["ipt_type"],
        "opt_type": correct_para["opt_type"],
        "res": correct_para["res"],
        "slon": slon,
        "elon": elon,
        "slat": slat,
        "elat": elat,
        "inter": [slon, elon, slat, elat, correct_para["res"]],
        "inter_extend": [slon - 1, elon + 1, slat - 1, elat + 1, correct_para["res"]],
        "tp_model": tp_model,
        "tp_obs": tp_obs,
        "current_modelpath": current_modelpath,
        "opt_m3": opt_m3,
        "opt_grd": opt_grd,
        "sta_info": meb.read_stadata_from_micaps3(_abs_path(correct_para["station_info"])),
    }
    logger.info(
        "开始降水订正(%s)：起报时间-%s, 预报时效-%03d",
        mode,
        report_time.strftime("%Y%m%d%H"),
        dtime,
    )
    dataset["grd_hislist_model"], dataset["grd_hislist_model_smooth"], dataset["sta_hislist_obs"] = _read_history(dataset)
    dataset["grd_current_model"], dataset["grd_current_model_smooth"] = _read_current(dataset)
    mask_grd = mesh_val(meb.read_griddata_from_nc(_abs_path(correct_para["mask_nc"])), dataset["inter_extend"])
    dataset["mask_array"] = mask_grd.data.squeeze()
    _gain_slice(dataset)
    return dataset


def _read_history(dataset):
    """按 his_year、his_day 读取历史模式格点和对应实况站点。"""
    logger.info("加载历史数据集")
    model_hislist, model_hislist_smooth, obs_hislist = [], [], []
    for del_year in range(0, his_year + 1):
        start_year = dataset["rpt"] + relativedelta(years=-del_year)
        start_time = start_year - timedelta(days=his_day)
        end_time = start_year + timedelta(days=-1 if del_year == 0 else his_day)
        while start_time <= end_time:
            try:
                obs_time = _get_obs_time(start_time, dataset["dtime"], dataset["ipt_model"], dataset["ipt_obs"])
                model_path = dataset["tp_model"].format(rpt=start_time, dtime=dataset["dtime"])
                obs_path = dataset["tp_obs"].format(rpt=obs_time)
                if os.path.exists(model_path) and os.path.exists(obs_path):
                    grd_history = _read_grid(model_path, dataset["ipt_type"], "历史")
                    if grd_history is None:
                        continue
                    grd_mesh = mesh_val(grd_history, dataset["inter_extend"])
                    sta_obs = meb.read_stadata_from_micaps3(obs_path)
                    sta_match = pd.merge(dataset["sta_info"], sta_obs, on=["id"], how="left")
                    obs_data = sta_match.data0_y
                    obs_data[np.isnan(obs_data)] = 0
                    sta_obs = dataset["sta_info"].copy()
                    sta_obs.data0 = obs_data
                    sta_obs = clear_to_num_greater_than(sta_obs, 0.0, 500.0)
                    sta_obs = clear_to_num_less_than(sta_obs, 0.0, 0.0)
                    model_hislist.append(grd_mesh)
                    model_hislist_smooth.append(smooth9(grd_mesh, smooth_num))
                    obs_hislist.append(sta_obs)
                else:
                    logger.error("历史数据缺失：%s.%03d", start_time.strftime("%Y%m%d%H"), dataset["dtime"])
            except Exception as exc:
                logger.error(exc)
            finally:
                start_time += timedelta(days=1)
    logger.info("历史数据读取成功")
    return model_hislist, model_hislist_smooth, obs_hislist


def _read_current(dataset):
    """读取当前模式格点，并插值到扩展范围。"""
    try:
        logger.info("加载当前模式数据")
        grd_current = _read_grid(dataset["current_modelpath"], dataset["ipt_type"], "当前模式")
        if grd_current is None:
            return None, None
        grd_mesh = mesh_val(grd_current, dataset["inter_extend"])
        return grd_mesh, grd_mesh.copy()
    except Exception:
        return None, None


def _gain_slice(dataset):
    """时效不超过 60 且范围超过 10 度时按 5 度分块，否则整域一块，四周外扩 expansion。"""
    split_block = (dataset["dtime"] <= 60) and (dataset["elon"] - dataset["slon"] > 10) and (dataset["elat"] - dataset["slat"] > 10)
    if split_block:
        dataset["center_lon_left"] = GetNumUp(dataset["slon"], dataset["elon"])
        dataset["center_lon_right"] = GetNumDown(dataset["slon"], dataset["elon"])
        dataset["center_lat_bottom"] = GetNumUp(dataset["slat"], dataset["elat"])
        dataset["center_lat_top"] = GetNumDown(dataset["slat"], dataset["elat"])
    else:
        dataset["center_lon_left"] = [dataset["slon"]]
        dataset["center_lon_right"] = [dataset["elon"]]
        dataset["center_lat_bottom"] = [dataset["slat"]]
        dataset["center_lat_top"] = [dataset["elat"]]
    dataset["large_lon_left"] = [i - expansion for i in dataset["center_lon_left"]]
    dataset["large_lon_right"] = [i + expansion for i in dataset["center_lon_right"]]
    dataset["large_lat_bottom"] = [i - expansion for i in dataset["center_lat_bottom"]]
    dataset["large_lat_top"] = [i + expansion for i in dataset["center_lat_top"]]


# 分块光流订正 / 整域 Cressman+频率匹配：见 cli/_process（读入 → 插件 → 写出）。
