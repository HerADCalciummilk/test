# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取运行参数与路径。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "conf.ini")
_RAW_INI_CACHE: Optional[Dict[str, str]] = None
_CONFIG_OVERRIDE: Optional[str] = None
_CONFIG_ENV = "NIMM_GRID_STAT_MERGE_INI"


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
    if _CONFIG_OVERRIDE:
        return _CONFIG_OVERRIDE
    env_path = os.environ.get(_CONFIG_ENV, "").strip()
    if env_path:
        return env_path
    return _default_ini_abs_path()


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按项目根目录解析。文件不存在时抛出 FileNotFoundError。
    同时写入环境变量，供多进程子进程继承同一 ini。
    """
    global _CONFIG_OVERRIDE, _RAW_INI_CACHE
    if path is None or not str(path).strip():
        _CONFIG_OVERRIDE = None
        os.environ.pop(_CONFIG_ENV, None)
        chosen = _default_ini_abs_path()
    else:
        chosen = _expand_path_maybe_relative_to_repo(str(path))
        if not os.path.isfile(chosen):
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _CONFIG_OVERRIDE = chosen
        os.environ[_CONFIG_ENV] = chosen
    _RAW_INI_CACHE = None
    return chosen


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


def _ini_float(key: str, default: float) -> float:
    v = _ini_get(key)
    return float(v) if v else default


def _ini_int(key: str, default: int) -> int:
    v = _ini_get(key)
    return int(v) if v else default


def _ini_float_list(key: str, default: List[float]) -> List[float]:
    v = _ini_get(key)
    if not v:
        return list(default)
    return [float(x.strip()) for x in v.split(",") if x.strip()]


def _parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def get_resolved_paths() -> Dict[str, str]:
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(
            _ini_get("log_file", "log/YYYYMMDD.txt")),
        "grid_path": _expand_path_maybe_relative_to_repo(_ini_get("grid_path", "")),
        "sta_path": _expand_path_maybe_relative_to_repo(_ini_get("sta_path", "")),
        "output_path": _expand_path_maybe_relative_to_repo(
            _ini_get("output_path", "resource/output/merge.m4")),
        "terr_path": _expand_path_maybe_relative_to_repo(_ini_get("terr_path", "")),
    }


def get_merge_params() -> Dict:
    domain = _ini_float_list("domain", [])
    raw = _get_raw_ini()
    if "b_use_heatflux_equation" in raw:
        heat_raw = raw["b_use_heatflux_equation"]
    else:
        heat_raw = raw.get("use_heatflux", "")
    return {
        "R": _ini_float("r", 200.0),
        "domain": domain if len(domain) == 6 else None,
        "b_use_heatflux_equation": _parse_bool(heat_raw, False),
        "hf_eq_iter_nums": _ini_int("hf_eq_iter_nums", 20),
        "sta_val_col": _ini_get("sta_val_col", "data0") or "data0",
        "sta_lon_col": _ini_get("sta_lon_col", "lon") or "lon",
        "sta_lat_col": _ini_get("sta_lat_col", "lat") or "lat",
        "grid_type": (_ini_get("grid_type", "m4") or "m4").lower(),
        "sta_type": (_ini_get("sta_type", "m3") or "m3").lower(),
        "outer_value": _ini_float("outer_value", 0.0),
    }
