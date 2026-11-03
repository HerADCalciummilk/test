# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取运行参数与路径。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "conf.ini")
_RAW_INI_CACHE: Optional[Dict[str, str]] = None
_CONFIG_OVERRIDE: Optional[str] = None
_CONFIG_ENV = "NIMM_INTERP_SG_CRESSMAN_INI"


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


def _ini_float(key: str, default: Optional[float] = None) -> Optional[float]:
    v = _ini_get(key)
    if not v:
        return default
    return float(v)


def _ini_int(key: str, default: int) -> int:
    v = _ini_get(key)
    return int(v) if v else default


def _ini_float_list(key: str, default: List[float]) -> List[float]:
    v = _ini_get(key)
    if not v:
        return list(default)
    return [float(x.strip()) for x in v.split(",") if x.strip()]


def get_resolved_paths() -> Dict[str, str]:
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(
            _ini_get("log_file", "log/YYYYMMDD.txt")),
        "sta_path": _expand_path_maybe_relative_to_repo(_ini_get("sta_path", "")),
        "background_path": _expand_path_maybe_relative_to_repo(
            _ini_get("background_path", "")),
        "grid_template_path": _expand_path_maybe_relative_to_repo(
            _ini_get("grid_template_path", "")),
        "output_path": _expand_path_maybe_relative_to_repo(
            _ini_get("output_path", "resource/output/cressman.m4")),
    }


def get_cressman_params() -> Dict:
    glon = _ini_float_list("glon", [])
    glat = _ini_float_list("glat", [])
    domain = _ini_float_list("domain", [])
    outer = _ini_get("outer_value")
    return {
        "r_list": _ini_float_list("r_list", [60000.0, 40000.0, 20000.0]),
        "nearNum": _ini_int("nearnum", 100),
        "outer_value": float(outer) if outer != "" else None,
        "glon": glon if len(glon) == 3 else None,
        "glat": glat if len(glat) == 3 else None,
        # domain: sou,nor,wst,est,dlon,dlat → glat=[sou,nor,dlat], glon=[wst,est,dlon]
        "domain": domain if len(domain) == 6 else None,
        "sta_type": (_ini_get("sta_type", "m3") or "m3").lower(),
        "background_type": (_ini_get("background_type", "m4") or "m4").lower(),
        "grid_template_type": (_ini_get("grid_template_type", "m4") or "m4").lower(),
    }


def build_glon_glat(
    glon: Optional[Sequence] = None,
    glat: Optional[Sequence] = None,
    domain: Optional[Sequence] = None,
) -> Optional[Tuple[List[float], List[float]]]:
    """由 glon/glat 或 domain 得到 ``([slon,elon,dlon],[slat,elat,dlat])``。"""
    if glon is not None and glat is not None and len(glon) == 3 and len(glat) == 3:
        return [float(x) for x in glon], [float(x) for x in glat]
    if domain is not None and len(domain) == 6:
        sou, nor, wst, est, dlon, dlat = [float(x) for x in domain]
        return [wst, est, dlon], [sou, nor, dlat]
    return None
