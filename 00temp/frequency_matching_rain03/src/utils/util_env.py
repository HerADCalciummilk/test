# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取路径默认值。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from utils.util_paths import REPO_ROOT, expand_repo_path

_MAIN_INI_REL = Path("resource") / "conf.ini"
_RAW_INI_CACHE: dict | None = None
_CONFIG_OVERRIDE: Path | None = None
_CONFIG_ENV = "NIMM_FREQUENCY_MATCHING_RAIN03_INI"
_OVERRIDE_ENV = "NIMM_FREQUENCY_MATCHING_RAIN03_PATH_OVERRIDES"
_CALL_OVERRIDES: dict = {}


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


def _default_ini_abs_path() -> Path:
    return (REPO_ROOT / _MAIN_INI_REL).resolve()


def _main_ini_abs_path() -> Path:
    if _CONFIG_OVERRIDE is not None:
        return _CONFIG_OVERRIDE
    env_path = os.environ.get(_CONFIG_ENV, "").strip()
    if env_path:
        return Path(env_path)
    return _default_ini_abs_path()


def set_main_ini(path=None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按项目根目录解析。文件不存在时抛出 FileNotFoundError。
    同时写入环境变量，供子进程继承同一 ini。
    """
    global _CONFIG_OVERRIDE, _RAW_INI_CACHE
    if path is None or not str(path).strip():
        _CONFIG_OVERRIDE = None
        os.environ.pop(_CONFIG_ENV, None)
        chosen = _default_ini_abs_path()
    else:
        chosen = expand_repo_path(str(path))
        if not chosen.is_file():
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _CONFIG_OVERRIDE = chosen
        os.environ[_CONFIG_ENV] = str(chosen)
    _RAW_INI_CACHE = None
    return str(chosen)


def set_call_overrides(overrides=None) -> None:
    """替换本次调用的路径覆盖，并写入环境变量供子进程继承。

    值为 ``None`` 的项忽略。``log_file`` 覆盖 ``log_file_template``。
    显式值替换 ini；ini 为空时 ``get_resolved_paths`` 仍用代码预设。
    """
    global _CALL_OVERRIDES
    cleaned = {}
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                cleaned[str(key).strip().lower()] = value
    _CALL_OVERRIDES = cleaned
    if cleaned:
        os.environ[_OVERRIDE_ENV] = json.dumps(cleaned)
    else:
        os.environ.pop(_OVERRIDE_ENV, None)


def clear_call_overrides() -> None:
    """清空本次调用覆盖。"""
    set_call_overrides(None)


def _active_path_overrides():
    if _CALL_OVERRIDES:
        return _CALL_OVERRIDES
    raw = os.environ.get(_OVERRIDE_ENV, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key).lower(): value for key, value in data.items() if value is not None}


def _get_raw_ini() -> dict:
    global _RAW_INI_CACHE
    if _RAW_INI_CACHE is not None:
        return _RAW_INI_CACHE
    ini_path = _main_ini_abs_path()
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
    overrides = _active_path_overrides()
    for out_key, ini_key in mapping.items():
        if ini_key in overrides and overrides[ini_key] is not None:
            base[out_key] = expand_repo_path(str(overrides[ini_key]))
            continue
        raw = _raw_path(ini_key)
        if raw:
            base[out_key] = expand_repo_path(raw)
    return base
