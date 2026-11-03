# -*- coding: utf-8 -*-
"""从 ``resource/mait_3.ini`` 读取路径与默认运行项。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "mait_3.ini")
_DEFAULT_CLIP = (70.0, 140.0, 0.0, 60.0, 0.1, 0.1)
_DEFAULT_PREDICT_VALID = tuple(range(3, 252 + 1, 3))
_RAW_INI_CACHE: Optional[Dict[str, str]] = None


def _abspath(p: str) -> str:
    return os.path.normpath(os.path.abspath(os.path.expanduser(p.strip())))


def _expand_path_maybe_relative_to_repo(p: str) -> str:
    s = p.strip()
    if not s:
        return s
    exp = os.path.expanduser(s)
    if os.path.isabs(exp):
        return _abspath(exp)
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(exp)))


def _main_ini_abs_path() -> str:
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(_MAIN_INI_REL)))


def _parse_kv_ini(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or s.startswith(";"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip().lower()
                if k:
                    out[k] = v.strip()
    except OSError:
        return {}
    return out


def _get_raw_ini() -> Dict[str, str]:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is None:
        _RAW_INI_CACHE = _parse_kv_ini(_main_ini_abs_path())
    return _RAW_INI_CACHE


def get_repo_root() -> str:
    """本包仓库根（``multi_rain_mait03_blending/``）。"""
    return _REPO_ROOT


def _ini_get(key: str, default: str = "") -> str:
    return _get_raw_ini().get(key.lower(), default)


def _parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def get_resolved_paths() -> Dict[str, str]:
    """路径字典：``log_file_template``、``para_ini``、``background_ini``、``beta_path_template``、``station_info``、``mask_dat``。"""
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(
            _ini_get("log_file", "log/YYYYMMDD.txt")),
        "para_ini": _expand_path_maybe_relative_to_repo(
            _ini_get("para_ini", "resource/para_3.ini")),
        "background_ini": _expand_path_maybe_relative_to_repo(
            _ini_get("background_ini", "resource/para_3_background.ini")),
        "beta_path_template": _expand_path_maybe_relative_to_repo(
            _ini_get("beta_path_template", "beta_3h/YYYYMMDDHH/%02d_%02d_TTT.info")),
        "station_info": _expand_path_maybe_relative_to_repo(
            _ini_get("station_info", "resource/station_info.txt")),
        "mask_dat": _expand_path_maybe_relative_to_repo(
            _ini_get("mask_dat", "resource/mask010.dat")),
    }


def get_default_clip_coords() -> List[float]:
    """写出裁剪六元组 ``lon0,lon1,lat0,lat1,dlon,dlat``。"""
    v = _ini_get("clip_coords")
    if not v:
        return list(_DEFAULT_CLIP)
    return [float(x.strip()) for x in v.split(",") if x.strip()]


def get_default_predict_valid_list() -> List[int]:
    """预报时效（小时），默认 3–252、步长 3。"""
    v = _ini_get("predict_valid_list")
    if not v:
        return list(_DEFAULT_PREDICT_VALID)
    return [int(x.strip()) for x in v.split(",") if x.strip()]


def get_default_is_obs_bjt() -> bool:
    return _parse_bool(_ini_get("is_obs_bj") or _ini_get("is_obs_bjt"), True)


def get_default_pro_count() -> int:
    """起报并行进程数（``is_multi=true`` 时使用）。"""
    v = _ini_get("pro_count")
    return int(v) if v else 3


def get_default_is_multi() -> bool:
    """多个起报是否用 ``SimpleParallelTool`` 多进程。"""
    return _parse_bool(_ini_get("is_multi"), False)


def get_default_is_interp() -> bool:
    return _parse_bool(_ini_get("is_interp"), False)
