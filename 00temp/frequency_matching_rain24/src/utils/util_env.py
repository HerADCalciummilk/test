# -*- coding: utf-8 -*-
"""从 ``resource/optimize_tp_24.ini`` 读取运行参数与路径。"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# 本文件位于 src/utils/，项目根为其上两级
_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "optimize_tp_24.ini")
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
    return _REPO_ROOT


def _ini_get(key: str, default: str = "") -> str:
    return _get_raw_ini().get(key.lower(), default)


def _ini_int(key: str, default: int) -> int:
    v = _ini_get(key)
    return int(v) if v else default


def _ini_float(key: str, default: float) -> float:
    v = _ini_get(key)
    return float(v) if v else default


def _ini_float_list(key: str, default: List[float]) -> List[float]:
    v = _ini_get(key)
    if not v:
        return default
    return [float(x.strip()) for x in v.split(",") if x.strip()]


def _ini_str_list(key: str, default: Optional[List[str]] = None) -> List[str]:
    v = _ini_get(key)
    if not v:
        return default or []
    return [x.strip() for x in v.split(",") if x.strip()]


def get_resolved_paths() -> Dict[str, str]:
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(_ini_get("log_file", "log/YYYYMMDD.txt")),
        "station_info": _expand_path_maybe_relative_to_repo(_ini_get("station_info", "resource/sta.m3")),
        "mask_nc": _expand_path_maybe_relative_to_repo(_ini_get("mask_nc", "resource/mask010.nc")),
        "default_plugin": _expand_path_maybe_relative_to_repo(_ini_get("default_plugin", "resource/ecmwf.json")),
    }


def _parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or not str(raw).strip():
        return default
    t = str(raw).strip().lower()
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    return default


def get_default_is_multi() -> bool:
    """是否多进程跑「起报×时效」任务；默认 true（贴近原 Pool 常开）。"""
    return _parse_bool(_ini_get("is_multi"), default=True)


def get_default_pro_count() -> int:
    """并行进程数：优先 ``pro_count``，否则回退旧键 ``pool_num``。"""
    v = _ini_get("pro_count")
    if v:
        return int(v)
    return _ini_int("pool_num", 4)


def get_runtime_config() -> Dict[str, Any]:
    clip = _ini_float_list("clip_coords", [70.0, 140.0, 0.0, 60.0])
    slon, elon, slat, elat = clip[0], clip[1], clip[2], clip[3]
    pro_count = get_default_pro_count()
    return {
        "rpt_list": _ini_str_list("rpt_list", []),
        "ipt_model": _ini_int("ipt_model", 0),
        "ipt_obs": _ini_int("ipt_obs", 1),
        "ipt_type": _ini_get("ipt_type", "m4"),
        "opt_type": _ini_get("opt_type", "m4"),
        "over_w": _ini_int("over_w", 0),
        "start_dtime": _ini_int("start_dtime", 36),
        "end_dtime": _ini_int("end_dtime", 252),
        "inter_dtime1": _ini_int("inter_dtime1", 12),
        "inter_dtime2": _ini_int("inter_dtime2", 12),
        "report_inter": _ini_int("report_inter", 12),
        "res": _ini_float("res", 0.1),
        "slon": slon,
        "elon": elon,
        "slat": slat,
        "elat": elat,
        "slon_l": slon - 1,
        "elon_l": elon + 1,
        "slat_l": slat - 1,
        "elat_l": elat + 1,
        "is_multi": get_default_is_multi(),
        "pro_count": pro_count,
        "pool_num": pro_count,  # 兼容旧名
    }
