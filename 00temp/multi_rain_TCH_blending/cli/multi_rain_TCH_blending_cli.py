# -*- coding: utf-8 -*-
"""TCH 多模式集成 24 小时降水。

无多进程需求，正文只在 ``process``：合参与公共准备后，按时效循环三段::

    1. 读入 —— 该时效多模式降水 + 掩膜展平
    2. 插件 —— 权重评估 / 加权合成
    3. 写出 —— 权重 info、格点 m4、站点 m3（含 micaps 副本）
"""
from __future__ import annotations

import datetime
import os
import sys

import numpy as np

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_SRC_DIR, _ROOT_DIR):
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import meteva.base as meb

from pre_fcst_tch_realtime import (
    build_title,
    clock,
    get_model_data,
    prepare_ensemble_for_tch,
    select_initial_time,
)
from tch_blend_plugin import TchBlendPlugin
from tch_weight_plugin import TchWeightPlugin
from utils.merge_params import merge_params
from utils.util_env import resolve_process_args


@merge_params()
def process(
    maskout_file: str = None,
    nx_mask: int = None,
    ny_mask: int = None,
    dir_model_data: str = None,
    dir_tch_output: str = None,
    ipt_type: str = None,
    model_list: list = None,
    grid_lon: list = None,
    grid_lat: list = None,
    fcst_hours: list = None,
    station_level: int = None,
    bjt_offset_hours: int = None,
    initial_hour_threshold: int = None,
    initial_hour_late: int = None,
    initial_hour_early: int = None,
    initial_time: str = None,
    config=None,
):
    """合参后串行跑各预报时效：读入 → 插件 → 写出。

    ``ipt_type`` 默认 ``nc``：优先读 ``.nc``，不存在再尝试 ``.m4``。
    """
    _ = config
    cfg = resolve_process_args(
        maskout_file=maskout_file,
        nx_mask=nx_mask,
        ny_mask=ny_mask,
        dir_model_data=dir_model_data,
        dir_tch_output=dir_tch_output,
        ipt_type=ipt_type,
        model_list=model_list,
        grid_lon=grid_lon,
        grid_lat=grid_lat,
        fcst_hours=fcst_hours,
        station_level=station_level,
        bjt_offset_hours=bjt_offset_hours,
        initial_hour_threshold=initial_hour_threshold,
        initial_hour_late=initial_hour_late,
        initial_hour_early=initial_hour_early,
        initial_time=initial_time,
    )

    # 公共准备（各时效共用）
    maskout_data = np.fromfile(cfg["maskout_file"], "f").reshape(
        (cfg["ny_mask"], cfg["nx_mask"]), order="C"
    )
    maskout_series = np.array(maskout_data).reshape(cfg["nx_mask"] * cfg["ny_mask"])
    station_infor_n = meb.read_station(meb.station_国家站)
    meb.set_stadata_coords(station_infor_n, level=cfg["station_level"])

    time_main = select_initial_time(
        clock(cfg["initial_time"]),
        cfg["initial_hour_threshold"],
        cfg["initial_hour_late"],
        cfg["initial_hour_early"],
    )
    trnow = datetime.datetime.strftime(
        time_main + datetime.timedelta(hours=cfg["bjt_offset_hours"]),
        "%Y-%m-%d %H:%M:%S %p",
    )
    trnow_utc = datetime.datetime.strftime(time_main, "%Y-%m-%d %H:%M:%S %p")
    date_str = trnow[0:4] + trnow[5:7] + trnow[8:10]
    time_str = trnow[11:13]

    for fcst_num in cfg["fcst_hours"]:
        out_dir = cfg["dir_tch_output"] + date_str
        os.makedirs(out_dir, exist_ok=True)
        file_tag = (
            trnow[2:4] + trnow[5:7] + trnow[8:10] + trnow[11:13]
            + "." + str(int(fcst_num)).zfill(3)
        )
        utc_tag = date_str + trnow_utc[11:13] + "." + str(int(fcst_num)).zfill(3)
        fname_info = out_dir + "/" + file_tag + ".info"

        # 1. 读入：该时效多模式降水 → 掩膜展平，供权重插件使用
        qpf_model = get_model_data(
            cfg["dir_model_data"],
            cfg["model_list"],
            time_main,
            fcst_num,
            cfg["grid_lon"],
            cfg["grid_lat"],
            ipt_type=cfg.get("ipt_type", "nc"),
        )
        if not hasattr(qpf_model, "dims") or "member" not in qpf_model.dims:
            raise RuntimeError(
                "时效 %s 没有读到任何模式降水：%s" % (fcst_num, cfg["dir_model_data"])
            )
        qpf_flat, ndim, _ny, _nx = prepare_ensemble_for_tch(qpf_model, maskout_series)
        members = list(qpf_model["member"].data)

        # 2. 核心插件
        #    TchWeightPlugin：对展平集合场做 TCH 不确定度评估，并算 BTCH 集成权重
        #    TchBlendPlugin：用权重对多模式格点加权合成，并插到站点
        weight_out = TchWeightPlugin().process(qpf_flat)
        uct, weights = weight_out["uct"], weight_out["weights"]
        blend_out = TchBlendPlugin().process(
            qpf_model, weights, station=station_infor_n
        )
        qpf_combine, sta_combine = blend_out["qpf_combine"], blend_out["sta_combine"]

        # 3. 写出：权重 info + 格点/站点（北京时与 UTC 两套路径）
        with open(fname_info, "w") as f_info:
            f_info.writelines("模式成员评估结果为：\n")
            f_info.writelines(str(np.round(uct, 4)) + "\n")
            f_info.writelines("模式成员及其权重系数为：\n")
            for rank_num in range(ndim):
                f_info.writelines(
                    str(members[rank_num])
                    + ":  "
                    + str(np.around(weights[rank_num], 4))
                    + "\n"
                )

        dtime = qpf_combine.dtime.data[0]
        title_bjt = build_title(trnow, time_str, dtime, "TCH")
        title_utc = build_title(trnow, trnow_utc[11:13], dtime, "TCH")
        meb.write_griddata_to_micaps4(
            qpf_combine, out_dir + "/" + file_tag, creat_dir=True,
            effectiveNum=1, title=title_bjt, show=True,
        )
        meb.write_stadata_to_micaps3(
            sta_combine, out_dir + "/" + file_tag + ".m3", creat_dir=True,
            effectiveNum=1, title=title_bjt, show=True,
        )
        meb.write_griddata_to_micaps4(
            qpf_combine, out_dir + "/micaps/" + utc_tag + ".m4", creat_dir=True,
            effectiveNum=1, title=title_utc, show=True,
        )
        meb.write_stadata_to_micaps3(
            sta_combine, out_dir + "/micaps/" + utc_tag + ".m3", creat_dir=True,
            effectiveNum=1, title=title_utc, show=True,
        )

    return 0
