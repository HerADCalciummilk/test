# -*- coding: utf-8 -*-
"""从 ``resource/gust_factor.ini`` 读取运行路径与默认参数。

约定：
- 路径可为相对本包根目录，或绝对路径；
- CLI 未给出的项回落到本 ini。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "gust_factor.ini")
_RAW_INI_CACHE: Optional[Dict[str, str]] = None


def _abspath(p: str) -> str:
    """规范化绝对路径。"""
    return os.path.normpath(os.path.abspath(os.path.expanduser(p.strip())))


def _expand_path_maybe_relative_to_repo(p: str) -> str:
    """相对路径按仓库根展开；空串原样返回。"""
    s = (p or "").strip()
    if not s:
        return s
    exp = os.path.expanduser(s)
    if os.path.isabs(exp):
        return _abspath(exp)
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(exp)))


def _main_ini_abs_path() -> str:
    return _abspath(os.path.join(_REPO_ROOT, os.path.normpath(_MAIN_INI_REL)))


def _parse_kv_ini(path: str) -> Dict[str, str]:
    """简单 key=value ini（#/; 注释，忽略空行）。"""
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
    """本包仓库根（``gust_factor/``）。"""
    return _REPO_ROOT


def _ini_get(key: str, default: str = "") -> str:
    return _get_raw_ini().get(key.lower(), default)


def _parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def _parse_int_tuple(raw: str, default: Tuple[int, ...]) -> Tuple[int, ...]:
    if not raw or not str(raw).strip():
        return tuple(default)
    return tuple(int(x.strip()) for x in str(raw).split(",") if x.strip())


def get_resolved_paths() -> Dict[str, str]:
    """解析后的路径字典（绝对路径）。"""
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(
            _ini_get("log_file", "log/YYYYMMDD.txt")
        ),
        "station_csv_dir": _expand_path_maybe_relative_to_repo(
            _ini_get("station_csv_dir", "resource/test_data")
        ),
        "factor_path": _expand_path_maybe_relative_to_repo(
            _ini_get("factor_path", "resource/output/gust_factor.json")
        ),
        "u_path": _expand_path_maybe_relative_to_repo(_ini_get("u_path", "")),
        "v_path": _expand_path_maybe_relative_to_repo(_ini_get("v_path", "")),
        "output_path": _expand_path_maybe_relative_to_repo(
            _ini_get("output_path", "resource/output/gust_out.nc")
        ),
        "ws_path": _expand_path_maybe_relative_to_repo(_ini_get("ws_path", "")),
        "png_path": _expand_path_maybe_relative_to_repo(
            _ini_get("png_path", "resource/output/WS_and_GUST.png")
        ),
    }


def get_run_params() -> Dict:
    """运行参数（模式、时效、是否出图）。"""
    return {
        "mode": (_ini_get("mode", "all") or "all").strip().lower(),
        "fore_hours": _parse_int_tuple(_ini_get("fore_hours"), (24, 48, 72)),
        "fore_hour": int(_ini_get("fore_hour") or "24"),
        "make_png": _parse_bool(_ini_get("make_png"), False),
        "show_png": _parse_bool(_ini_get("show_png"), False),
    }


def clear_ini_cache() -> None:
    """测试用：清空 ini 缓存。"""
    global _RAW_INI_CACHE
    _RAW_INI_CACHE = None
