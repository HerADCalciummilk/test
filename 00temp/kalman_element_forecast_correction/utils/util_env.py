# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
日期留空时由调用方按「前一天」处理，不在这里填具体日期。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

PRESET: Dict[str, Dict[str, Any]] = {
    "kalman": {
        "start_date": "",
        "end_date": "",
        "base_dir": "/data234/GUO_data/Kalman_data",
        "obs_root": "/data234/DataPool/01CLDAS/00HRCLDAS/Hourly",
        "alpha": 0.15,
        "back_days": 5,
        "variables": "SWVL,STL",
        "obs_end_time": "",
    },
    "trans": {
        "date": "",
        "swvl_source": "/data/mnt/model_RT/globalECMWF_D1D/SWVL",
        "stl_source": "/data/mnt/model_RT/globalECMWF_D1D/STL",
        "target_base": "/data234/GUO_data/Kalman_data/process_data",
    },
}

_MODULE_ALIASES = {"kalman_data": "kalman", "trans_data": "trans"}
_MODULES = ("kalman", "trans")


def clear_ini_cache() -> None:
    global _CACHE
    _CACHE = None


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按本包目录解析。文件不存在时抛出 ``FileNotFoundError``。
    返回实际使用的绝对路径。
    """
    global _INI_PATH, _CACHE
    if path is None or not str(path).strip():
        _INI_PATH = _DEFAULT_INI
        chosen = _DEFAULT_INI
    else:
        raw = Path(str(path).strip()).expanduser()
        chosen = raw if raw.is_absolute() else (_PKG_ROOT / raw)
        chosen = chosen.resolve()
        if not chosen.is_file():
            raise FileNotFoundError(f"配置文件不存在: {chosen}")
        _INI_PATH = chosen
    _CACHE = None
    return str(chosen)


def _parser() -> configparser.ConfigParser:
    global _CACHE
    if _CACHE is None:
        parser = configparser.ConfigParser()
        if _INI_PATH.is_file():
            parser.read(_INI_PATH, encoding="utf-8")
        _CACHE = parser
    return _CACHE


def _raw(section: str, key: str) -> Optional[str]:
    parser = _parser()
    if not parser.has_section(section) or not parser.has_option(section, key):
        return None
    value = parser.get(section, key).strip()
    return value or None


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _expand(path: str) -> str:
    expanded = Path(path).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return str((_PKG_ROOT / expanded).resolve())


def _opt_str(section: str, key: str, preset: str, *, path: bool = False) -> str:
    raw = _raw(section, key)
    value = preset if raw is None else raw
    if path and value:
        return _expand(value)
    return value


def _opt_int(section: str, key: str, preset: int) -> int:
    raw = _raw(section, key)
    return preset if raw is None else int(raw)


def _opt_float(section: str, key: str, preset: float) -> float:
    raw = _raw(section, key)
    return preset if raw is None else float(raw)


def _pick_str(explicit: Optional[str], fallback: str) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    return fallback


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    """选择 kalman 或 trans。显式参数优先，否则读 ``[cli] module``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_module(module)
    finally:
        if config:
            set_main_ini(None)


def _resolve_module(module: Optional[str] = None) -> str:
    if _missing(module):
        module = _raw("cli", "module") or ""
    name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
    if name not in _MODULES:
        raise ValueError(
            "module 未指定或无效。请传 --module，可选 kalman（或 kalman_data）、trans（或 trans_data）"
        )
    return name


def resolve_kalman(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    base_dir: Optional[str] = None,
    obs_root: Optional[str] = None,
    alpha: Optional[float] = None,
    back_days: Optional[int] = None,
    variables: Optional[str] = None,
    obs_end_time: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐订正参数。日期为空表示调用方使用前一天。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_kalman(
            start_date=start_date,
            end_date=end_date,
            base_dir=base_dir,
            obs_root=obs_root,
            alpha=alpha,
            back_days=back_days,
            variables=variables,
            obs_end_time=obs_end_time,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_kalman(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    base_dir: Optional[str] = None,
    obs_root: Optional[str] = None,
    alpha: Optional[float] = None,
    back_days: Optional[int] = None,
    variables: Optional[str] = None,
    obs_end_time: Optional[str] = None,
) -> Dict[str, Any]:
    preset = PRESET["kalman"]
    return {
        "start_date": _pick_str(start_date, _opt_str("kalman", "start_date", str(preset["start_date"]))),
        "end_date": _pick_str(end_date, _opt_str("kalman", "end_date", str(preset["end_date"]))),
        "base_dir": _pick_str(base_dir, _opt_str("kalman", "base_dir", str(preset["base_dir"]), path=True)),
        "obs_root": _pick_str(obs_root, _opt_str("kalman", "obs_root", str(preset["obs_root"]), path=True)),
        "alpha": float(_opt_float("kalman", "alpha", float(preset["alpha"])) if alpha is None else alpha),
        "back_days": int(_opt_int("kalman", "back_days", int(preset["back_days"])) if back_days is None else back_days),
        "variables": _pick_str(variables, _opt_str("kalman", "variables", str(preset["variables"]))),
        "obs_end_time": _pick_str(
            obs_end_time, _opt_str("kalman", "obs_end_time", str(preset["obs_end_time"]))
        ),
    }


def resolve_trans(
    date: Optional[str] = None,
    swvl_source: Optional[str] = None,
    stl_source: Optional[str] = None,
    target_base: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, str]:
    """补齐拷贝参数。日期为空表示调用方使用前一天。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_trans(
            date=date,
            swvl_source=swvl_source,
            stl_source=stl_source,
            target_base=target_base,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_trans(
    date: Optional[str] = None,
    swvl_source: Optional[str] = None,
    stl_source: Optional[str] = None,
    target_base: Optional[str] = None,
) -> Dict[str, str]:
    preset = PRESET["trans"]
    return {
        "date": _pick_str(date, _opt_str("trans", "date", str(preset["date"]))),
        "swvl_source": _pick_str(
            swvl_source, _opt_str("trans", "swvl_source", str(preset["swvl_source"]), path=True)
        ),
        "stl_source": _pick_str(
            stl_source, _opt_str("trans", "stl_source", str(preset["stl_source"]), path=True)
        ),
        "target_base": _pick_str(
            target_base, _opt_str("trans", "target_base", str(preset["target_base"]), path=True)
        ),
    }
