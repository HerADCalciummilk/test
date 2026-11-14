# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
源格点与目标网格（或模板）留空时直接报错，不猜测路径。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, List, Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

PRESET: Dict[str, Any] = {
    "module": "linear",
    "used_coords": "xy",
    "outer_value": 0.0,
}

_MODULE_ALIASES = {
    "gg_linear": "linear",
    "interp_gg_linear": "linear",
    "gg_nearest": "nearest",
    "interp_gg_nearest": "nearest",
    "gg_cubic": "cubic",
    "interp_gg_cubic": "cubic",
}
_MODULES = ("linear", "nearest", "cubic")


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


def _parse_float_list(value: Any) -> Optional[List[float]]:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return [float(p) for p in parts] if parts else None
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    raise ValueError("须为逗号分隔字符串或数值序列")


def _optional_float(explicit: Optional[float], section: str, key: str) -> Optional[float]:
    if explicit is not None:
        return float(explicit)
    raw = _raw(section, key)
    return None if raw is None else float(raw)


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
    grid_template: Optional[str] = None,
    output: Optional[str] = None,
    used_coords: Optional[str] = None,
    outer_value: Optional[float] = None,
    glon: Any = None,
    glat: Any = None,
    domain: Any = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            module=module,
            grid=grid,
            grid_template=grid_template,
            output=output,
            used_coords=used_coords,
            outer_value=outer_value,
            glon=glon,
            glat=glat,
            domain=domain,
        )
    finally:
        if config:
            set_main_ini(None)


def _pick_float_list(
    explicit: Any, section: str, key: str, n: Optional[int] = None
) -> Optional[List[float]]:
    if explicit is not None:
        parsed = _parse_float_list(explicit)
    else:
        raw = _raw(section, key)
        parsed = _parse_float_list(raw) if raw is not None else None
    if parsed is not None and n is not None and len(parsed) != n:
        raise ValueError(f"{key} 须为 {n} 个数")
    return parsed


def _resolve_args(
    module: Optional[str] = None,
    grid: Optional[str] = None,
    grid_template: Optional[str] = None,
    output: Optional[str] = None,
    used_coords: Optional[str] = None,
    outer_value: Optional[float] = None,
    glon: Any = None,
    glat: Any = None,
    domain: Any = None,
) -> Dict[str, Any]:
    name = resolve_module(module)
    resolved: Dict[str, Any] = {
        "module": name,
        "grid": _require("grid", grid, "input", "grid"),
        "grid_template": _optional_path(grid_template, "input", "grid_template"),
        "output": _optional_path(output, "output", "path"),
    }

    # used_coords / outer_value：优先读当前 module 节，再回退 [linear]
    coords = (
        used_coords.strip()
        if not _missing(used_coords)
        else (
            _raw(name, "used_coords")
            or _raw("linear", "used_coords")
            or str(PRESET["used_coords"])
        )
    )
    if coords != "xy":
        raise ValueError('used_coords 当前仅支持 "xy"')
    resolved["used_coords"] = coords

    if outer_value is not None:
        resolved["outer_value"] = float(outer_value)
    else:
        raw = _raw(name, "outer_value")
        if raw is None:
            raw = _raw("linear", "outer_value")
        resolved["outer_value"] = float(PRESET["outer_value"]) if raw is None else float(raw)

    resolved["glon"] = _pick_float_list(glon, "target", "glon", n=3)
    resolved["glat"] = _pick_float_list(glat, "target", "glat", n=3)
    resolved["domain"] = _pick_float_list(domain, "target", "domain", n=6)

    has_glon_glat = resolved["glon"] is not None and resolved["glat"] is not None
    has_domain = resolved["domain"] is not None
    has_template = resolved["grid_template"] is not None
    if not (has_glon_glat or has_domain or has_template):
        raise ValueError(
            "无法确定目标网格：请提供 --glon+--glat，或 --domain，或 --grid-template / ini 对应项"
        )
    if has_glon_glat and (resolved["glon"] is None or resolved["glat"] is None):
        raise ValueError("glon 与 glat 须同时给出")
    return resolved
