# -*- coding: utf-8 -*-
"""逐 3 小时降水频率匹配订正。

一条任务 = 一个起报 ``date_time`` × 一个时效 ``predict_valid``。
``pro_count>1`` 时 ``process`` 把 ``_process`` 交给进程池。

``_process`` 三段::

    1. 读入 —— path/config/站点/掩膜，展开输出路径
    2. 插件 —— ``FrequencyMatchingRain03Plugin.process``
    3. 写出 —— 在插件内完成（m3/m4/nc）
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")


def _prefer_path(*dirs):
    # insert(0) 逆序落地：最后一项在 sys.path 最前
    for d in dirs:
        if not d:
            continue
        d = os.path.normpath(d)
        while d in sys.path:
            sys.path.remove(d)
        sys.path.insert(0, d)


# 与 rain24 相同：最终 ROOT 在前，走包级 utils/__init__（合并 00temp/utils + src/utils）
_prefer_path(_SRC_DIR, _ROOT_DIR)
for _k in list(sys.modules):
    if _k == "utils" or _k.startswith("utils."):
        del sys.modules[_k]
import utils  # noqa: E402,F401

from frequency_matching_rain03_plugin import FrequencyMatchingRain03Plugin
from frequency_matching_rain03_plugin_util import (
    _build_forecast_tasks,
    _load_grid_config,
    _load_mask_grid,
    _load_path_configs,
)
from utils.io_meb import expand_data_path
from utils.log import Log
from utils.merge_params import merge_params
from utils.multipro_plugin import SimpleParallelTool
from utils.types import FileFlag, LineData, ScatterData


def _abs_path(path):
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


def _is_datetime_token(token):
    text = str(token).strip()
    return text.isdigit() and len(text) in (10, 12)


def _parse_token(token):
    text = str(token).strip()
    if len(text) == 10 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d%H")
    if len(text) == 12 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d%H%M")
    raise ValueError("Date Args Content Is Not Right!")


def _expand_run_times(run_times):
    if run_times is None:
        return [datetime.now()]
    items = _as_list(run_times)
    dts = [item if isinstance(item, datetime) else _parse_token(item) for item in items]
    if len(dts) == 1:
        return dts
    if len(dts) == 2:
        start, end = dts
        if start > end:
            raise ValueError("Date Args Range Is Not Right!")
        out = []
        current = start
        while current <= end:
            out.append(current)
            current += timedelta(hours=1)
        return out
    raise ValueError("Date Args Number Is Not Right!")


def _para_for(configs, default_key, data_key, log):
    key = (str(data_key).strip() if data_key else "") or None
    if not key:
        if default_key and default_key in configs:
            key = default_key
        elif len(configs) == 1:
            key = next(iter(configs))
        else:
            log.write_error("Data Key Is Not Specified!", 1)
            raise RuntimeError("Data Key Is Not Specified!")
    para = configs.get(key)
    if para is None:
        log.write_error("Data Key Is Not Exist! key=%s" % key, 1)
        raise RuntimeError("Data Key Is Not Exist! key=%s" % key)
    return para, key


def _process(
    date_time,
    predict_valid,
    *,
    data_key,
    log_file,
    config_json,
    path_json,
    station_info,
    mask_file,
):
    """订正一个起报时效：读入 → 插件.process → 写出（插件内）。"""
    if date_time is None or predict_valid is None:
        return
    try:
        when = date_time if not isinstance(date_time, str) else _parse_token(date_time)
        lead = int(predict_valid)
        log_path = _abs_path(log_file) if log_file else log_file
        log = Log(expand_data_path(log_path, datetime.now(), 0))

        # 1. 读入：路径配置、网格、站点、掩膜
        configs, default_key = _load_path_configs(
            Path(_ROOT_DIR), log, path_json=_abs_path(path_json) if path_json else path_json
        )
        para, _key = _para_for(configs, default_key, data_key, log)
        configure_data = _load_grid_config(
            Path(_ROOT_DIR),
            log,
            config_json=_abs_path(config_json) if config_json else config_json,
        )
        station_file = _abs_path(station_info) if station_info else station_info
        if not os.path.exists(station_file):
            raise RuntimeError("Station info file not found: %s" % station_file)
        sd_sta_info = ScatterData(station_file, FileFlag.stainfo)
        sd_sta_info = sd_sta_info.frame_by_line(
            LineData(
                [
                    configure_data.large_lon_left,
                    configure_data.large_lon_right,
                    configure_data.large_lon_right,
                    configure_data.large_lon_left,
                ],
                [
                    configure_data.large_lat_bottom,
                    configure_data.large_lat_bottom,
                    configure_data.large_lat_top,
                    configure_data.large_lat_top,
                ],
            )
        )
        mask_src = _abs_path(mask_file) if mask_file else mask_file
        resource_dir = Path(mask_src).parent
        resolution = configure_data.dlon
        if abs(resolution - 0.01) < 0.001:
            mask_name = "mask001.dat"
        elif abs(resolution - 0.05) < 0.001:
            mask_name = "mask005.dat"
        else:
            mask_name = "mask010.dat"
        mask_path = resource_dir / mask_name
        if not mask_path.exists():
            log.write_info("%s not found, fallback to mask file argument" % mask_name, 0)
            mask_path = Path(mask_src)
        if not mask_path.exists():
            raise RuntimeError("Mask file not found: %s" % mask_path)
        gd_mask = _load_mask_grid(str(mask_path), configure_data.dlon)

        # 2. 核心插件：历史相似 + 频率匹配 +（短时效）光流外推 + Cressman 上格点
        # 3. 写出：插件内写 m3 / m4 / nc
        FrequencyMatchingRain03Plugin(
            para["model_template"],
            para["fact_template"],
            para["output_template"],
            configure_data,
            sd_sta_info,
            gd_mask,
            log,
        ).process(when, lead)
    except Exception as exc:
        logging.getLogger("frequency_matching_rain03").error(
            "订正失败 date_time=%s lead=%s: %s", date_time, predict_valid, exc
        )


@merge_params()
def process(
    run_times: Optional[List[str]] = None,
    pro_count: int = 1,
    *,
    data_key: str = None,
    log_file: str = None,
    config_json: str = None,
    path_json: str = None,
    station_info: str = None,
    mask_file: str = None,
    config=None,
):
    """展开全部起报时效；pro_count>1 时并行调用 _process。"""
    _ = config
    tasks = _build_forecast_tasks(_expand_run_times(run_times))
    if not tasks:
        raise ValueError("缺少参数: run_times（调用参数与配置文件均未提供）")
    correct_para = {
        "data_key": data_key,
        "log_file": log_file,
        "config_json": config_json,
        "path_json": path_json,
        "station_info": station_info,
        "mask_file": mask_file,
    }
    date_times = [when for when, _lead in tasks]
    leads = [lead for _when, lead in tasks]
    if int(pro_count or 1) > 1:
        sw_all = datetime.now()
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=int(pro_count),
            fixed_params=correct_para,
        ).process({"date_time": date_times, "predict_valid": leads})
        print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
    else:
        for date_time, predict_valid in zip(date_times, leads):
            _process(date_time, predict_valid, **correct_para)
