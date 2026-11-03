# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取路径与默认运行项。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

_UTIL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_UTIL_DIR))
_MAIN_INI_REL = os.path.join("resource", "conf.ini")
_DEFAULT_CLIP = (70.0, 140.0, 0.0, 60.0, 0.1, 0.1)
_DEFAULT_PREDICT_VALID = tuple(range(3, 252 + 1, 3))
_RAW_INI_CACHE: Optional[Dict[str, str]] = None
_CONFIG_OVERRIDE: Optional[str] = None
_CONFIG_ENV = "NIMM_MULTI_RAIN_MAIT03_BLENDING_INI"


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
    """本包仓库根（``multi_rain_mait03_blending/``）。"""
    return _REPO_ROOT


def _ini_get(key: str, default: str = "") -> str:
    return _get_raw_ini().get(key.lower(), default)


def _ini_first(*keys: str, default: str) -> str:
    """按顺序取第一个非空 ini 值；都空则用代码预设。"""
    raw = _get_raw_ini()
    for key in keys:
        v = raw.get(key.lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _parse_bool(raw: Optional[str], default: bool = False) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def get_resolved_paths() -> Dict[str, str]:
    """路径字典：``log_file_template``、``para_ini``、``background_ini``、``beta_path_template``、``station_info``、``mask_dat``。

    ini 键用 ``process`` 参数名（``para_path``、``background_path``、``beta_path``）；
    仍接受旧键 ``para_ini``、``background_ini``、``beta_path_template``。空值回落到代码预设。
    """
    return {
        "log_file_template": _expand_path_maybe_relative_to_repo(
            _ini_first("log_file", default="log/YYYYMMDD.txt")),
        "para_ini": _expand_path_maybe_relative_to_repo(
            _ini_first("para_path", "para_ini", default="resource/para_3.ini")),
        "background_ini": _expand_path_maybe_relative_to_repo(
            _ini_first("background_path", "background_ini", default="resource/para_3_background.ini")),
        "beta_path_template": _expand_path_maybe_relative_to_repo(
            _ini_first(
                "beta_path", "beta_path_template", "bate_file", "beta_file",
                default="beta_3h/YYYYMMDDHH/%02d_%02d_TTT.info",
            )),
        "station_info": _expand_path_maybe_relative_to_repo(
            _ini_first("station_info", default="resource/station_info.txt")),
        "mask_dat": _expand_path_maybe_relative_to_repo(
            _ini_first("mask_dat", "mask_nc", default="resource/mask010.dat")),
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
    raw = _get_raw_ini()
    chosen = None
    for key in ("is_obs_bjt", "is_obs_bj"):
        v = raw.get(key)
        if v is not None and str(v).strip():
            chosen = v
            break
    return _parse_bool(chosen, True)


def get_default_pro_count() -> int:
    """起报并行进程数（``is_multi=true`` 时使用）。"""
    v = _ini_get("pro_count")
    return int(v) if v else 3


def get_default_is_multi() -> bool:
    """多个起报是否用 ``SimpleParallelTool`` 多进程。"""
    return _parse_bool(_ini_get("is_multi"), False)


def get_default_is_interp() -> bool:
    return _parse_bool(_ini_get("is_interp"), False)
