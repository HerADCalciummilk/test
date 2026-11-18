# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
源格点与目标站点留空时直接报错，不猜测路径。
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
    "module": "linear",
    "used_coords": "xy",
}

_MODULE_ALIASES = {
    "gs_linear": "linear",
    "interp_gs_linear": "linear",
    "gs_nearest": "nearest",
    "interp_gs_nearest": "nearest",
    "gs_cubic": "cubic",
    "interp_gs_cubic": "cubic",
}
_MODULES = ("linear", "nearest", "cubic")
_LINEAR_COORDS = ("xy", "xyz", "xydt")


def clear_ini_cache() -> None:
    global _CACHE
    _CACHE = None


def set_main_ini(path: Optional[str] = None) -> str:
    """切换运行配置 ini，并清空缓存。"""
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


def _optional_str(explicit: Optional[str], section: str, key: str) -> Optional[str]:
    if not _missing(explicit):
        return str(explicit).strip()
    return _raw(section, key)


def resolve_io_type(path: str, explicit: Optional[str] = None) -> str:
    """解析源格点格式：显式 ``nc`` / ``m4`` 优先；否则按扩展名（``.nc``→nc，否则 m4）。"""
    if not _missing(explicit):
        name = str(explicit).strip().lower()
        if name not in ("nc", "m4"):
            raise ValueError(f"格点格式须为 nc 或 m4，收到: {explicit!r}")
        return name
    return "nc" if str(path).lower().endswith(".nc") else "m4"


def resolve_sta_type(path: str, explicit: Optional[str] = None) -> str:
    """解析站点格式：显式 ``csv`` / ``m3`` 优先；否则按扩展名（``.csv``→csv，否则 m3）。"""
    if not _missing(explicit):
        name = str(explicit).strip().lower()
        if name not in ("csv", "m3"):
            raise ValueError(f"站点格式须为 csv 或 m3，收到: {explicit!r}")
        return name
    return "csv" if str(path).lower().endswith(".csv") else "m3"


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    if config:
        set_main_ini(config)
    try:
        if _missing(module):
            module = _raw("cli", "module") or str(PRESET["module"])
        name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
        if name not in _MODULES:
            raise ValueError(
                "module 未指定或无效。请传 --module，可选 linear、nearest、cubic"
            )
        return name
    finally:
        if config:
            set_main_ini(None)


def resolve_args(
    module: Optional[str] = None,
    grid: Optional[str] = None,
    sta: Optional[str] = None,
    output: Optional[str] = None,
    used_coords: Optional[str] = None,
    grid_type: Optional[str] = None,
    sta_type: Optional[str] = None,
    output_type: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            module=module,
            grid=grid,
            sta=sta,
            output=output,
            used_coords=used_coords,
            grid_type=grid_type,
            sta_type=sta_type,
            output_type=output_type,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    module: Optional[str] = None,
    grid: Optional[str] = None,
    sta: Optional[str] = None,
    output: Optional[str] = None,
    used_coords: Optional[str] = None,
    grid_type: Optional[str] = None,
    sta_type: Optional[str] = None,
    output_type: Optional[str] = None,
) -> Dict[str, Any]:
    name = resolve_module(module)
    resolved: Dict[str, Any] = {
        "module": name,
        "grid": _require("grid", grid, "input", "grid"),
        "sta": _require("sta", sta, "input", "sta"),
        "output": _optional_path(output, "output", "path"),
    }

    # used_coords 仅 linear 使用；nearest / cubic 为固定水平插值
    if name == "linear":
        coords = (
            used_coords.strip()
            if not _missing(used_coords)
            else (
                _raw("linear", "used_coords")
                or str(PRESET["used_coords"])
            )
        )
        if coords not in _LINEAR_COORDS:
            raise ValueError(
                f'module="linear" 的 used_coords 仅支持 {_LINEAR_COORDS}，收到: {coords!r}'
            )
        resolved["used_coords"] = coords
    else:
        if not _missing(used_coords):
            raise ValueError(
                f'module={name!r} 不支持 used_coords（仅 linear 可用 xy/xyz/xydt）'
            )
        resolved["used_coords"] = None

    explicit_grid_type = _optional_str(grid_type, "input", "grid_type")
    explicit_sta_type = _optional_str(sta_type, "input", "sta_type")
    resolved["grid_type"] = resolve_io_type(resolved["grid"], explicit_grid_type)
    resolved["sta_type"] = resolve_sta_type(resolved["sta"], explicit_sta_type)

    if resolved["output"]:
        explicit_out = _optional_str(output_type, "output", "type")
        resolved["output_type"] = resolve_sta_type(resolved["output"], explicit_out)
    else:
        resolved["output_type"] = None

    return resolved
