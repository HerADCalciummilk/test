# -*- coding: utf-8 -*-
"""频率匹配 rain03：路径/网格/掩膜/任务展开（供 CLI 读入与 plugin 使用）。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from proc import StringProcess
from utils.io_meb import expand_data_path, find_grid_file
from utils.log import Log
from utils.types import ConfigureData, GridData
from utils.util_env import get_resolved_paths


_MASK_LON_START = 70.0
_MASK_LON_END = 140.0
_MASK_LAT_START = 0.0
_MASK_LAT_END = 60.0
_MASK_RESOLUTIONS = (0.01, 0.05, 0.1)


def _load_path_configs(base: Path, log: Log, path_json=None):
    """读 ``path.json``，返回 ``{key: {model,fact,output}_template}`` 与 ``default`` 键。"""
    if path_json is None:
        paths = get_resolved_paths()
        path_json = Path(paths["path_json"])
    else:
        path_json = Path(path_json)
    if not path_json.exists():
        log.write_error("Path Json File Is Not Exist!", 1)
        raise RuntimeError("Path Json File Is Not Exist!")
    try:
        payload = json.loads(path_json.read_text(encoding="utf-8"))
    except Exception as exc:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!") from exc
    default_key = None
    raw_configs = {}
    if isinstance(payload, dict) and isinstance(payload.get("configs"), dict):
        raw_configs = payload["configs"]
        if isinstance(payload.get("default"), str):
            default_key = payload["default"]
    elif isinstance(payload, dict):
        raw_configs = payload
    else:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    configs = {}
    for key, cfg in raw_configs.items():
        if not isinstance(cfg, dict):
            continue
        mt = cfg.get("model_template")
        ft = cfg.get("fact_template")
        ot = cfg.get("output_template")
        if all(isinstance(v, str) and v.strip() for v in [mt, ft, ot]):
            configs[str(key)] = {
                "model_template": mt.strip(),
                "fact_template": ft.strip(),
                "output_template": ot.strip(),
            }
    if not configs:
        log.write_error("Path Json Content Is Not Right!", 1)
        raise RuntimeError("Path Json Content Is Not Right!")
    return configs, default_key


def _load_grid_config(base: Path, log: Log, config_json=None):
    """读 ``config.json`` 的中心区与分辨率；缺省 70–140°E、0–60°N、0.1°、外扩 1°。"""
    cfg = ConfigureData()
    cfg.center_lon_left = 70.0
    cfg.center_lon_right = 140.0
    cfg.center_lat_bottom = 0.0
    cfg.center_lat_top = 60.0
    cfg.dlon = 0.1
    cfg.dlat = 0.1
    cfg.lonlat_ext = 1.0
    if config_json is None:
        paths = get_resolved_paths()
        config_path = Path(paths["config_json"])
    else:
        config_path = Path(config_json)
    if not config_path.exists():
        log.write_info("config.json not found, using default grid config", 0)
        return cfg
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.write_error(f"Failed to read config.json: {e}, using defaults", 1)
        return cfg
    if not isinstance(raw, dict):
        return cfg
    grid = raw.get("grid", raw)
    if not isinstance(grid, dict):
        return cfg
    cfg.center_lon_left = float(grid.get("lon_start", cfg.center_lon_left))
    cfg.center_lon_right = float(grid.get("lon_end", cfg.center_lon_right))
    cfg.center_lat_bottom = float(grid.get("lat_start", cfg.center_lat_bottom))
    cfg.center_lat_top = float(grid.get("lat_end", cfg.center_lat_top))
    cfg.dlon = float(grid.get("dlon", cfg.dlon))
    cfg.dlat = float(grid.get("dlat", cfg.dlat))
    cfg.lonlat_ext = float(grid.get("expand", cfg.lonlat_ext))
    log.write_info("config.json loaded successfully", 0)
    return cfg


def _mask_shape_for_resolution(resolution):
    xn = int(round((_MASK_LON_END + 1e-05 - _MASK_LON_START) / resolution)) + 1
    yn = int(round((_MASK_LAT_END + 1e-05 - _MASK_LAT_START) / resolution)) + 1
    return xn, yn


def _load_mask_grid(mask_path, preferred_resolution):
    mask_path = Path(mask_path)
    byte_size = mask_path.stat().st_size
    if byte_size % 4 != 0:
        raise RuntimeError(f"Mask file byte size is not a float32 grid: {mask_path}")

    value_count = byte_size // 4
    resolutions = [preferred_resolution]
    resolutions.extend(res for res in _MASK_RESOLUTIONS if abs(res - preferred_resolution) >= 1e-10)

    for resolution in resolutions:
        xn, yn = _mask_shape_for_resolution(resolution)
        if xn * yn == value_count:
            gd_mask = GridData(
                _MASK_LON_START, _MASK_LON_END,
                _MASK_LAT_START, _MASK_LAT_END,
                resolution, resolution)
            gd_mask.read_float_val_from_bin(str(mask_path))
            return gd_mask

    expected = ", ".join(
        f"{res:g}deg={_mask_shape_for_resolution(res)[0] * _mask_shape_for_resolution(res)[1]}"
        for res in _MASK_RESOLUTIONS)
    raise RuntimeError(
        f"Mask file size does not match supported full-grid masks: {mask_path}; "
        f"values={value_count}; expected {expected}")


def _build_forecast_tasks(run_dts):
    """每个起报回溯 0–24 h 再减 8 h，与时效 3–252（步长 3）做成任务表。"""
    num = 24  # 回溯小时数（再减 8 h 对齐北京时）
    cycles = list(dict.fromkeys(
        run_dt - timedelta(hours=h + 8) for run_dt in run_dts for h in range(num + 1)
    ))
    return [
        (date_time, predict_valid)
        for date_time in cycles
        for predict_valid in range(3, 252 + 1, 3)
    ]


def describe_task_io(model_tpl, output_tpl, date_time, predict_valid):
    """展开输出/模式路径，无后缀时尝试 ``.m4`` / ``.nc``。"""
    desc = StringProcess.date_replace("YYYYMMDDHH_VVV", date_time, predict_valid)
    out_m3 = expand_data_path(output_tpl + ".m3", date_time, predict_valid)
    out_m4 = expand_data_path(output_tpl + ".m4", date_time, predict_valid)
    model_raw, model_path = find_grid_file(model_tpl, date_time, predict_valid)
    return {
        "desc": desc,
        "out_m3": out_m3,
        "out_m4": out_m4,
        "model_raw": model_raw,
        "model_path": model_path,
        "output_exists": os.path.exists(out_m3) and os.path.exists(out_m4),
        "model_missing": model_path is None,
    }


# 兼容旧名
_describe_task_io = describe_task_io
