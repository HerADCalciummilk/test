# -*- coding: utf-8 -*-
"""从 ``resource/interp_sg_cressman.ini`` 读取运行参数与路径。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "interp_sg_cressman.ini")
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
