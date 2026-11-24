# -*- coding: utf-8 -*-
"""逐 1 小时降水频率匹配订正。

一条任务是一个起报循环 ``dt_input1``。该循环内的 1–48 时效留在这一条任务里。
``pro_count`` 大于 1 时，``process`` 把 ``_process`` 交给进程池。
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
_TEMP = os.path.dirname(_ROOT_DIR)
for _p in (_SRC_DIR, _TEMP, _ROOT_DIR):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from runner import (
    FACT_LEVEL,
    FINAL_FACT_LEVEL,
    SIMILAR_LEVEL,
    RunEnvPaths,
    _load_grid_config,
    _load_path_configs,
    _process_cycle,
    _resolve_para,
)
from utils.merge_params import merge_params
from utils.log import Log
from utils.multipro_plugin import SimpleParallelTool
from utils.string_process import date_replace


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


def _parse_run_times(run_times):
    """把一个时刻或起止时刻展开成逐小时列表。"""
    if run_times is None:
        return [datetime.now()]
    items = _as_list(run_times)
    dts = []
    for item in items:
        if isinstance(item, datetime):
            dts.append(item)
            continue
        token = str(item).strip()
        if len(token) == 12 and token.isdigit():
            dts.append(datetime.strptime(token, "%Y%m%d%H%M"))
        else:
            raise ValueError("Date Args Content Is Not Right!")
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


def _cycles(run_times):
    """由运行时刻反推需要订正的起报循环。"""
    run_dts = _parse_run_times(run_times)
    return list(dict.fromkeys(
        run_dt - timedelta(hours=hour + 8) for run_dt in run_dts for hour in range(25)
    ))


def _process(
    dt_input1,
    *,
    data_key,
    log_file,
    config_json,
    path_json,
    station_info,
    mask_file,
    sample_workers,
    block_workers,
    fixed_seed,
    valid_workers,
):
    """订正一个起报循环。时效 1–48 在本任务内串行。"""
    if not dt_input1:
        return
    try:
        when = dt_input1
        if isinstance(when, str):
            when = datetime.strptime(when, "%Y%m%d%H%M")
        log_path = _abs_path(log_file) if log_file else log_file
        log = Log(date_replace(log_path, datetime.now(), 0))
        configs, default_key = _load_path_configs(
            None, log, path_json=_abs_path(path_json) if path_json else path_json)
        para = _resolve_para(data_key, configs, default_key, log)
        grid_cfg = _load_grid_config(
            None, log, config_json=_abs_path(config_json) if config_json else config_json)
        env_paths = RunEnvPaths(
            log_file_template=Path(log_path),
            config_json=Path(_abs_path(config_json) if config_json else config_json),
            path_json=Path(_abs_path(path_json) if path_json else path_json),
            station_info=Path(_abs_path(station_info) if station_info else station_info),
            mask_resource_dir=Path(_abs_path(mask_file) if mask_file else mask_file).parent,
        )
        errors = _process_cycle(
            env_paths,
            para,
            when,
            FACT_LEVEL,
            SIMILAR_LEVEL,
            FINAL_FACT_LEVEL,
            int(sample_workers),
            int(block_workers),
            grid_cfg,
            None if fixed_seed is None else int(fixed_seed),
            int(valid_workers),
        )
        for err in errors:
            log.write_error(err, 1)
    except Exception as exc:
        logging.getLogger("frequency_matching_rain01").error(
            "订正失败 dt_input1=%s: %s", dt_input1, exc)


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
    sample_workers: int = 4,
    block_workers: int = 1,
    fixed_seed: Optional[int] = None,
    valid_workers: int = 1,
    config=None,
):
    """展开全部起报循环；pro_count 大于 1 时并行调用 _process。"""
    cycles = _cycles(run_times)
    if not cycles:
        raise ValueError("缺少参数: run_times（调用参数与配置文件均未提供）")
    correct_para = {
        "data_key": data_key,
        "log_file": log_file,
        "config_json": config_json,
        "path_json": path_json,
        "station_info": station_info,
        "mask_file": mask_file,
        "sample_workers": sample_workers,
        "block_workers": block_workers,
        "fixed_seed": fixed_seed,
        "valid_workers": valid_workers,
    }
    if pro_count > 1:
        sw_all = datetime.now()
        SimpleParallelTool(
            target_func=_process,
            parallel_mode="async",
            with_return=True,
            num_process=pro_count,
            fixed_params=correct_para,
        ).process({"dt_input1": cycles})
        print(">>> Time elasped: " + str((datetime.now() - sw_all).total_seconds()))
    else:
        for dt_input1 in cycles:
            _process(dt_input1, **correct_para)
