# -*- coding: utf-8 -*-
"""从 ``resource/qpf_fm.ini`` 读取路径默认值。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.util_paths import REPO_ROOT, expand_repo_path

_MAIN_INI_REL = Path("resource") / "qpf_fm.ini"
_RAW_INI_CACHE: dict | None = None


def _parse_kv_ini(path: Path) -> dict:
    out = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip().lower()
        if k:
            out[k] = v.strip()
    return out


def _get_raw_ini() -> dict:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is not None:
        return _RAW_INI_CACHE
    ini_path = REPO_ROOT / _MAIN_INI_REL
    _RAW_INI_CACHE = _parse_kv_ini(ini_path) if ini_path.is_file() else {}
    return _RAW_INI_CACHE


def _raw_path(key: str):
    v = _get_raw_ini().get(key.lower())
    if v is None or not str(v).strip():
        return None
    return str(v).strip()


def _defaults_paths_resolved() -> dict:
    return {
        "log_file_template": expand_repo_path("log/YYYYMMDD.txt"),
        "config_json": expand_repo_path("resource/config.json"),
        "path_json": expand_repo_path("resource/path.json"),
        "station_info": expand_repo_path("resource/sta.info"),
        "mask_file": expand_repo_path("resource/mask010.dat"),
    }


def get_resolved_paths() -> dict:
    """日志、config/path JSON、站点表、掩膜的绝对路径（相对项相对仓库根）。"""
    base = _defaults_paths_resolved().copy()
    mapping = {
        "log_file_template": "log_file",
        "config_json": "config_json",
        "path_json": "path_json",
        "station_info": "station_info",
        "mask_file": "mask_file",
    }
    for out_key, ini_key in mapping.items():
        raw = _raw_path(ini_key)
        if raw:
            base[out_key] = expand_repo_path(raw)
    return base
