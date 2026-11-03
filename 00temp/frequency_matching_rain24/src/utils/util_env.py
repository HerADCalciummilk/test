# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取运行参数与路径。"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

# 本文件位于 src/utils/，项目根为其上两级
_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "conf.ini")
_RAW_INI_CACHE: Optional[Dict[str, str]] = None
_CONFIG_OVERRIDE: Optional[str] = None
# 本次 process 调用的显式参数。非 None 覆盖 ini，空则回落到预设。
_CALL_OVERRIDES: Dict[str, Any] = {}


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


def _default_ini_abs_path() -> str:
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(_MAIN_INI_REL)))


def _main_ini_abs_path() -> str:
    return _CONFIG_OVERRIDE or _default_ini_abs_path()


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按项目根目录解析。返回实际使用的绝对路径。
    """
    global _CONFIG_OVERRIDE, _RAW_INI_CACHE
    if path is None or not str(path).strip():
        _CONFIG_OVERRIDE = None
        chosen = _default_ini_abs_path()
    else:
        chosen = _expand_path_maybe_relative_to_repo(str(path))
        if not os.path.isfile(chosen):
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _CONFIG_OVERRIDE = chosen
    _RAW_INI_CACHE = None
    return chosen


def set_call_overrides(overrides: Optional[Dict[str, Any]] = None) -> None:
    """替换本次调用的参数覆盖。

    值为 ``None`` 的项忽略。传入 ``None`` 或空映射即清空。
    显式值在 ``get_runtime_config`` / ``get_resolved_paths`` 里替换 ini，
    ini 为空时才用代码预设。
    """
    global _CALL_OVERRIDES
    cleaned: Dict[str, Any] = {}
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                cleaned[str(key).strip().lower()] = value
    _CALL_OVERRIDES = cleaned


def clear_call_overrides() -> None:
    """清空本次调用覆盖。"""
    set_call_overrides(None)


def get_call_overrides() -> Dict[str, Any]:
    """当前覆盖的副本，供子进程固定参数带回。"""
    return dict(_CALL_OVERRIDES)


def _has_override(key: str) -> bool:
    return key.lower() in _CALL_OVERRIDES


def _override(key: str) -> Any:
    return _CALL_OVERRIDES[key.lower()]


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


def _resolved_path(ini_key: str, preset: str) -> str:
    """显式覆盖 > 非空 ini > 预设。"""
    if _has_override(ini_key):
        text = str(_override(ini_key)).strip()
    else:
        text = _ini_get(ini_key)
        if not text:
            text = preset
    return _expand_path_maybe_relative_to_repo(text)


def get_resolved_paths() -> Dict[str, str]:
    return {
        "log_file_template": _resolved_path("log_file", "log/YYYYMMDD.txt"),
        "station_info": _resolved_path("station_info", "resource/sta.m3"),
        "mask_nc": _resolved_path("mask_nc", "resource/mask010.nc"),
        "default_plugin": _resolved_path("default_plugin", "resource/ecmwf.json"),
    }


def _parse_bool(raw: Optional[Any], default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
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
    if _has_override("is_multi"):
        return _parse_bool(_override("is_multi"), default=True)
    return _parse_bool(_ini_get("is_multi"), default=True)


def get_default_pro_count() -> int:
    """并行进程数：显式 ``pro_count`` > ini ``pro_count`` > 旧键 ``pool_num``。"""
    if _has_override("pro_count"):
        return int(_override("pro_count"))
    v = _ini_get("pro_count")
    if v:
        return int(v)
    return _ini_int("pool_num", 4)


def _runtime_int(key: str, preset: int) -> int:
    if _has_override(key):
        return int(_override(key))
    return _ini_int(key, preset)


def _runtime_float(key: str, preset: float) -> float:
    if _has_override(key):
        return float(_override(key))
    return _ini_float(key, preset)


def _runtime_str(key: str, preset: str) -> str:
    if _has_override(key):
        return str(_override(key))
    value = _ini_get(key)
    return value if value else preset


def _runtime_rpt_list() -> List[str]:
    if _has_override("rpt_list"):
        raw = _override("rpt_list")
        if isinstance(raw, str):
            return [item.strip() for item in raw.split(",") if item.strip()]
        return [str(item).strip() for item in list(raw) if str(item).strip()]
    return _ini_str_list("rpt_list", [])


def _runtime_clip_coords() -> List[float]:
    preset = [70.0, 140.0, 0.0, 60.0]
    if _has_override("clip_coords"):
        raw = _override("clip_coords")
        if isinstance(raw, str):
            clip = [float(item.strip()) for item in raw.split(",") if item.strip()]
        else:
            clip = [float(item) for item in raw]
        if len(clip) != 4:
            raise ValueError("clip_coords 需要 4 个浮点数: slon,elon,slat,elat")
        return clip
    return _ini_float_list("clip_coords", preset)


def get_runtime_config() -> Dict[str, Any]:
    clip = _runtime_clip_coords()
    slon, elon, slat, elat = clip[0], clip[1], clip[2], clip[3]
    pro_count = get_default_pro_count()
    return {
        "rpt_list": _runtime_rpt_list(),
        "ipt_model": _runtime_int("ipt_model", 0),
        "ipt_obs": _runtime_int("ipt_obs", 1),
        "ipt_type": _runtime_str("ipt_type", "m4"),
        "opt_type": _runtime_str("opt_type", "m4"),
        "over_w": _runtime_int("over_w", 0),
        "start_dtime": _runtime_int("start_dtime", 36),
        "end_dtime": _runtime_int("end_dtime", 252),
        "inter_dtime1": _runtime_int("inter_dtime1", 12),
        "inter_dtime2": _runtime_int("inter_dtime2", 12),
        "report_inter": _runtime_int("report_inter", 12),
        "res": _runtime_float("res", 0.1),
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
