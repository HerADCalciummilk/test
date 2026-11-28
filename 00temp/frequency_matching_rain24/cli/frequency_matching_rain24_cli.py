# -*- coding: utf-8 -*-
"""频率匹配 24h CLI。

一条任务 = 一个起报 × 一个时效。``_process`` 三段::

    1. 读入 —— 准备插件所需全部数据与后端
    2. 插件 —— 只调 ``*.process()``（光流分块 / 插值整域）
    3. 写出 —— 站点 m3、格点 m4/nc

``match_mode`` 只换 Cressman / 外推实现（估 UV 始终 OpticalFlow）::

    aligned（默认）: cressman_project_innov（InterpSg degree_blend=0.85 的旧签名封装）+ LagrangianAligned
    original:        InterpSg(method="cressman", reprocess=True, degree_blend=1.0) + Lagrangian

示例::

    python -m cli
    python -m cli match_mode=aligned config=resource/conf_aligned.ini
    python -m cli match_mode=original config=resource/conf.ini
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import meteva.base as meb

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")


def _prefer_path(*dirs):
    for d in dirs:
        if not d:
            continue
        d = os.path.normpath(d)
        while d in sys.path:
            sys.path.remove(d)
        sys.path.insert(0, d)


_prefer_path(_SRC_DIR, _ROOT_DIR)
for _k in list(sys.modules):
    if _k == "utils" or _k.startswith("utils."):
        del sys.modules[_k]
import utils  # noqa: E402

from utils.merge_params import merge_params
from utils.logger import logger
from utils.multipro_plugin import SimpleParallelTool

from frequency_matching_rain24_plugin import (
    CressmanFreqMatchGridPlugin,
    OpticalFlowSliceCorrectPlugin,
)
import frequency_matching_rain24_plugin_util as util

_MODE_HINT_INI = {
    "original": "resource/conf.ini",
    "aligned": "resource/conf_aligned.ini",
}


def _process(plugin, report_time, dtime, match_mode="aligned", **correct_para):
    """订正一个起报时效：读入 → 插件.process → 写出。"""
    mode = util._normalize_mode(match_mode)
    try:
        # 1. 读入：历史/当前/掩码/分块 + 本任务 Cressman/外推后端
        dataset = util._load_dataset(
            plugin, report_time, dtime, correct_para, match_mode=mode
        )
        if dataset is None:
            return
        cressman_slice, cressman_grid, lagrangian_cls = util._cressman_and_lagrangian(mode)

        # 2. 核心插件（只调 process）
        #    光流路径：分块 OpticalFlow + 外推 + 块内 Cressman
        correct_sta = OpticalFlowSliceCorrectPlugin(
            dataset,
            cressman_fn=cressman_slice,
            lagrangian_cls=lagrangian_cls,
        ).process()
        if correct_sta is None:
            raise RuntimeError("切片订正结果为空")
        #    插值路径：整域 Cressman + FrequencyMatch（无光流）
        correct_grd = CressmanFreqMatchGridPlugin(
            dataset,
            correct_sta,
            cressman_fn=cressman_grid,
        ).process()

        # 3. 写出站点 m3 与格点 m4/nc。
        meb.write_stadata_to_micaps3(
            correct_sta, save_path=dataset["opt_m3"], effectiveNum=2, creat_dir=True, show=True
        )
        if dataset["opt_type"] == "m4":
            meb.write_griddata_to_micaps4(
                correct_grd, save_path=dataset["opt_grd"], creat_dir=True, effectiveNum=1, show=True
            )
        elif dataset["opt_type"] == "nc":
            meb.write_griddata_to_nc(
                correct_grd, save_path=dataset["opt_grd"], creat_dir=True, effectiveNum=1, show=True
            )
        else:
            raise ValueError("输出格点文件类型设置有误，当前仅支持 m4 和 nc")
    except Exception as exc:
        logger.error("订正失败(%s) report=%s dtime=%s: %s", mode, report_time, dtime, exc)


@merge_params(anchor=__file__)
def process(
    match_mode: str = "aligned",
    plugin=None,
    rpt_times: list = None,
    pro_count: int = 1,
    station_info: str = None,
    mask_nc: str = None,
    ipt_model: int = 0,
    ipt_obs: int = 1,
    ipt_type: str = "m4",
    opt_type: str = "m4",
    over_w: int = 0,
    start_dtime: int = 36,
    end_dtime: int = 252,
    inter_dtime1: int = 12,
    inter_dtime2: int = 12,
    report_inter: int = 12,
    res: float = 0.1,
    clip_coords: tuple = (70.0, 140.0, 0.0, 60.0),
    config=None,
):
    """展开起报×时效；``pro_count>1`` 时并行调 ``_process``。"""
    mode = util._normalize_mode(match_mode)
    if not plugin:
        raise ValueError(
            "缺少参数: plugin。默认 aligned 可用 config=resource/conf_aligned.ini；"
            "原版请用 config=resource/conf.ini（或显式 plugin=...）"
        )
    if not rpt_times:
        raise ValueError("缺少参数: rpt_times（调用参数与配置文件均未提供）")
    logger.info("frequency matching mode=%s（建议配置 %s）", mode, _MODE_HINT_INI[mode])

    correct_para = {
        "station_info": station_info,
        "mask_nc": mask_nc,
        "ipt_model": ipt_model,
        "ipt_obs": ipt_obs,
        "ipt_type": ipt_type,
        "opt_type": opt_type,
        "over_w": over_w,
        "res": res,
        "clip_coords": clip_coords,
    }
    report_times = []
    dtimes = []
    for report_time in util._expand_report_times(rpt_times, report_inter):
        for dtime in util._expand_dtime_list(
            start_dtime, end_dtime, inter_dtime1, inter_dtime2
        ):
            report_times.append(report_time)
            dtimes.append(dtime)

    fixed = {"plugin": plugin, "match_mode": mode, **correct_para}
    count = int(pro_count or 1)
    if count > 1:
        sw_all = datetime.now()
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=count,
            fixed_params=fixed,
        ).process({"report_time": report_times, "dtime": dtimes})
        print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
    else:
        for report_time, dtime in zip(report_times, dtimes):
            _process(report_time=report_time, dtime=dtime, **fixed)
