# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

PRESET: Dict[str, Any] = {
    "weight_power": -2.0,
    "tolerate_period_mismatch": False,
}


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


def _opt_float(section: str, key: str, preset: float) -> float:
    raw = _raw(section, key)
    return preset if raw is None else float(raw)


def _opt_bool(section: str, key: str, preset: bool) -> bool:
    raw = _raw(section, key)
    if raw is None:
        return preset
    text = raw.lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    return preset


def resolve_args(
    weight_power: Optional[float] = None,
    tolerate_period_mismatch: Optional[bool] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐权重指数和时效容错开关。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            weight_power=weight_power,
            tolerate_period_mismatch=tolerate_period_mismatch,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    weight_power: Optional[float] = None,
    tolerate_period_mismatch: Optional[bool] = None,
) -> Dict[str, Any]:
    return {
        "weight_power": (
            _opt_float("blend", "weight_power", float(PRESET["weight_power"]))
            if weight_power is None
            else float(weight_power)
        ),
        "tolerate_period_mismatch": (
            _opt_bool("blend", "tolerate_period_mismatch", bool(PRESET["tolerate_period_mismatch"]))
            if tolerate_period_mismatch is None
            else bool(tolerate_period_mismatch)
        ),
    }
