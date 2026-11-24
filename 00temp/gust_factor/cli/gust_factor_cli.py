# -*- coding: utf-8 -*-
"""阵风系数调度。

``@merge_params`` 挂在 ``process`` 上。按 mode 读站点或 U/V，调用两个插件，写出系数或阵风场。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
for _p in (_SRC_DIR, _ROOT_DIR):
    sys.path.insert(0, _p)

from utils.merge_params import merge_params
from utils.util_env import get_repo_root


def _abs_repo(path):
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return text
    raw = Path(text).expanduser()
    if raw.is_absolute():
        return str(raw)
    return str((Path(get_repo_root()) / raw).resolve())


def _fore_hours(value):
    if value is None:
        return (24, 48, 72)
    if isinstance(value, (list, tuple)):
        return tuple(int(item) for item in value)
    text = str(value).strip()
    if not text:
        return (24, 48, 72)
    return tuple(int(item.strip()) for item in text.split(",") if item.strip())


@merge_params()
def process(
    mode: str = "all",
    station_csv_dir=None,
    fore_hours: list = None,
    factor_path=None,
    u_path=None,
    v_path=None,
    fore_hour: int = 24,
    output_path=None,
    make_png: bool = False,
    show_png: bool = False,
    ws_path=None,
    png_path=None,
    log_file=None,
    config=None,
):
    """算阵风系数和/或订正阵风。``config`` 只换配置文件。``log_file`` 为配置项，调度不另开日志。"""
    _ = config
    _ = log_file
    import numpy as np

    from gust_factor import (
        GustCorrectWithFactorPlugin,
        GustFactorCalculatorPlugin,
        load_station_csv_dir,
        make_compare_png,
        read_grid_nc,
        write_grid_nc,
    )

    mode = (mode or "all").strip().lower()
    if mode not in ("calc", "correct", "all"):
        raise ValueError("未知 mode=%r，期望 calc/correct/all" % mode)
    station_csv_dir = _abs_repo(station_csv_dir)
    factor_path = _abs_repo(factor_path)
    u_path = _abs_repo(u_path)
    v_path = _abs_repo(v_path)
    output_path = _abs_repo(output_path)
    ws_path = _abs_repo(ws_path) if ws_path else ""
    png_path = _abs_repo(png_path)
    hours = _fore_hours(fore_hours)
    hour = int(fore_hour)
    result = {"mode": mode, "repo_root": get_repo_root()}

    if mode in ("calc", "all"):
        print("#" * 60)
        print("start calculate gust factor")
        print("#" * 60)
        train_pd = load_station_csv_dir(station_csv_dir)
        g_factor = GustFactorCalculatorPlugin().process(
            train_pd, fore_hours=hours, save_path=factor_path or ""
        )
        result["gust_factor"] = g_factor
        result["factor_path"] = factor_path

    if mode in ("correct", "all"):
        print("#" * 60)
        print("start use gust factor to correct gust forecast")
        print("#" * 60)
        u_da = read_grid_nc(u_path)
        v_da = read_grid_nc(v_path)
        g_da = GustCorrectWithFactorPlugin().process(u_da, v_da, hour, factor_path)
        write_grid_nc(g_da, output_path)
        print("阵风预报结果已保存至：%s" % output_path)
        result["output_path"] = output_path
        result["fore_hour"] = hour
        if make_png and ws_path:
            ws_da = read_grid_nc(ws_path)
            ws_arr = np.asarray(ws_da.values)[0, 0, 0, 0]
            gust_arr = np.asarray(g_da.values)[0, 0, 0, 0]
            make_compare_png(ws_arr, gust_arr, png_path, show_png)
            result["png_path"] = png_path
    return result
