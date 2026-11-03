# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
站点文件和格点文件留空时直接报错，不猜测路径。
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
    "module": "total",
    "effect_r": 1000,
    "near_num": 8,
    "decrease": 2,
    "half_r": 20,
    "delta_effect_r": 400,
    "delta_near_num": 10,
    "delta_decrease": 2,
}

_MODULE_ALIASES = {"delta": "idw_delta", "idw-delta": "idw_delta"}
_MODULES = ("total", "idw", "idw_delta", "gaussian")


def clear_ini_cache() -> None:
    global _CACHE
    _CACHE = None


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。

    ``path`` 为空时回到 ``resource/conf.ini``。
    相对路径按项目根目录解析。文件不存在时抛出 ``FileNotFoundError``。
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


def _opt_int(section: str, key: str, preset: int) -> int:
    raw = _raw(section, key)
    return preset if raw is None else int(raw)


def _pick_int(explicit: Optional[int], section: str, key: str, preset: int) -> int:
    if explicit is None:
        return _opt_int(section, key, preset)
    return int(explicit)


def _require(name: str, explicit: Optional[str], section: str, key: str) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        raise ValueError(
            f"{name} 未指定。请传对应命令行参数，或在 resource/conf.ini 的 [{section}] 中填写 {key}"
        )
    return _expand(raw)


def _optional_path(explicit: Optional[str], section: str, key: str) -> Optional[str]:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        return None
    return _expand(raw)


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    """选择融合方式。显式参数优先，否则读 ``[cli] module``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。
    """
    if config:
        set_main_ini(config)
    try:
        if _missing(module):
            module = _raw("cli", "module") or str(PRESET["module"])
        name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
        if name not in _MODULES:
            raise ValueError("module 未指定或无效。请传 --module，可选 total、idw、idw_delta、gaussian")
        return name
    finally:
        if config:
            set_main_ini(None)


def resolve_args(
    module: Optional[str] = None,
    sta: Optional[str] = None,
    grid: Optional[str] = None,
    background: Optional[str] = None,
    effect_r: Optional[int] = None,
    near_num: Optional[int] = None,
    decrease: Optional[int] = None,
    half_r: Optional[int] = None,
    delta_effect_r: Optional[int] = None,
    delta_near_num: Optional[int] = None,
    delta_decrease: Optional[int] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐命令行参数。``config`` 给出时改读该 ini，返回前恢复默认文件。"""
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            module=module,
            sta=sta,
            grid=grid,
            background=background,
            effect_r=effect_r,
            near_num=near_num,
            decrease=decrease,
            half_r=half_r,
            delta_effect_r=delta_effect_r,
            delta_near_num=delta_near_num,
            delta_decrease=delta_decrease,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    module: Optional[str] = None,
    sta: Optional[str] = None,
    grid: Optional[str] = None,
    background: Optional[str] = None,
    effect_r: Optional[int] = None,
    near_num: Optional[int] = None,
    decrease: Optional[int] = None,
    half_r: Optional[int] = None,
    delta_effect_r: Optional[int] = None,
    delta_near_num: Optional[int] = None,
    delta_decrease: Optional[int] = None,
) -> Dict[str, Any]:
    name = resolve_module(module)
    resolved: Dict[str, Any] = {
        "module": name,
        "sta": _require("sta", sta, "input", "sta"),
        "grid": _require("grid", grid, "input", "grid"),
        "background": _optional_path(background, "input", "background"),
    }
    if name == "gaussian":
        resolved["half_r"] = _pick_int(half_r, "gaussian", "half_r", int(PRESET["half_r"]))
        if resolved["half_r"] <= 0:
            raise ValueError("half_r 必须大于 0")
        return resolved

    resolved["effect_r"] = _pick_int(effect_r, name, "effect_r", int(PRESET["effect_r"]))
    resolved["near_num"] = _pick_int(near_num, name, "near_num", int(PRESET["near_num"]))
    resolved["decrease"] = _pick_int(decrease, name, "decrease", int(PRESET["decrease"]))
    if resolved["effect_r"] <= 0:
        raise ValueError("effect_r 必须大于 0")
    if resolved["near_num"] < 1:
        raise ValueError("near_num 必须大于等于 1")
    if name == "total":
        resolved["delta_effect_r"] = _pick_int(
            delta_effect_r, "total", "delta_effect_r", int(PRESET["delta_effect_r"])
        )
        resolved["delta_near_num"] = _pick_int(
            delta_near_num, "total", "delta_near_num", int(PRESET["delta_near_num"])
        )
        resolved["delta_decrease"] = _pick_int(
            delta_decrease, "total", "delta_decrease", int(PRESET["delta_decrease"])
        )
    return resolved
