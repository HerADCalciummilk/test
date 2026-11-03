# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
除 ``summary`` 外，降水数值留空时直接报错。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

METHODS = ("summary", "db", "box", "nq", "sqrt")

PRESET: Dict[str, Any] = {
    "method": "summary",
    "threshold": 0.1,
    "lambda": 0.0,
    "a": 0.0,
    "inverse": False,
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


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _opt_str(section: str, key: str, preset: str) -> str:
    raw = _raw(section, key)
    return preset if raw is None else raw


def _first_float(section: str, keys, preset: float) -> float:
    for key in keys:
        raw = _raw(section, key)
        if raw is not None:
            return float(raw)
    return preset


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
    method: Optional[str] = None,
    values: Optional[str] = None,
    threshold: Optional[float] = None,
    zerovalue: Optional[float] = None,
    lam: Optional[float] = None,
    a: Optional[float] = None,
    inverse: Optional[bool] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐命令行参数。``zerovalue`` 为 ``None`` 时交给变换函数自己的默认值。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            method=method,
            values=values,
            threshold=threshold,
            zerovalue=zerovalue,
            lam=lam,
            a=a,
            inverse=inverse,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    method: Optional[str] = None,
    values: Optional[str] = None,
    threshold: Optional[float] = None,
    zerovalue: Optional[float] = None,
    lam: Optional[float] = None,
    a: Optional[float] = None,
    inverse: Optional[bool] = None,
) -> Dict[str, Any]:
    name = method.strip() if not _missing(method) else _opt_str("cli", "method", str(PRESET["method"]))
    if name not in METHODS:
        raise ValueError("method 无效。可选 summary、db、box、nq、sqrt")
    resolved_values = values.strip() if not _missing(values) else _raw("transform", "values")
    if name != "summary" and _missing(resolved_values):
        raise ValueError("values 未指定。请传 --values，或在 resource/conf.ini 的 [transform] 中填写")
    resolved_zero = zerovalue
    if resolved_zero is None:
        raw_zero = _raw("transform", "zerovalue")
        resolved_zero = None if raw_zero is None else float(raw_zero)
    return {
        "method": name,
        "values": None if _missing(resolved_values) else str(resolved_values).strip(),
        "threshold": (
            _opt_float("transform", "threshold", float(PRESET["threshold"]))
            if threshold is None
            else float(threshold)
        ),
        "zerovalue": resolved_zero,
        "lambda": float(lam) if lam is not None else _first_float(
            "transform", ("lam", "lambda"), float(PRESET["lambda"])
        ),
        "a": _opt_float("transform", "a", float(PRESET["a"])) if a is None else float(a),
        "inverse": _opt_bool("transform", "inverse", bool(PRESET["inverse"])) if inverse is None else bool(inverse),
    }
