# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
路径、起报时间和时效列表留空时直接报错。
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
    "module": "timesplit",
    "interp_method": "slinear",
    "is_fill0": False,
    "ntime": 10,
    "is_min": True,
    "index": "dtime",
}

_MODULE_ALIASES = {
    "time_split": "timesplit",
    "hour_to_min": "hourtomin",
    "readdata": "read",
}
_MODULES = ("timesplit", "hourtomin", "read")


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


def _opt_int(section: str, key: str, preset: int) -> int:
    raw = _raw(section, key)
    return preset if raw is None else int(raw)


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


def _optional(explicit: Optional[str], section: str, key: str) -> Optional[str]:
    if not _missing(explicit):
        return str(explicit).strip()
    return _raw(section, key)


def _require(name: str, explicit: Optional[str], section: str, key: str) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        raise ValueError(
            f"{name} 未指定。请传对应命令行参数，或在 resource/conf.ini 的 [{section}] 中填写 {key}"
        )
    return raw


def resolve_module(module: Optional[str] = None) -> str:
    if _missing(module):
        module = _raw("cli", "module") or str(PRESET["module"])
    name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
    if name not in _MODULES:
        raise ValueError("module 未指定或无效。请传 --module，可选 timesplit、hourtomin、read")
    return name


def resolve_args(
    module: Optional[str] = None,
    input_fh: Optional[str] = None,
    output_fh: Optional[str] = None,
    interp_method: Optional[str] = None,
    input_fmt: Optional[str] = None,
    time: Optional[str] = None,
    output_fmt: Optional[str] = None,
    uv_fmt: Optional[str] = None,
    delta_hour: Optional[str] = None,
    is_fill0: Optional[bool] = None,
    ntime: Optional[int] = None,
    is_min: Optional[bool] = None,
    index: Optional[str] = None,
    file_path: Optional[str] = None,
    file_time: Optional[str] = None,
    glon: Optional[str] = None,
    glat: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐命令行参数。``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。"""
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            module=module,
            input_fh=input_fh,
            output_fh=output_fh,
            interp_method=interp_method,
            input_fmt=input_fmt,
            time=time,
            output_fmt=output_fmt,
            uv_fmt=uv_fmt,
            delta_hour=delta_hour,
            is_fill0=is_fill0,
            ntime=ntime,
            is_min=is_min,
            index=index,
            file_path=file_path,
            file_time=file_time,
            glon=glon,
            glat=glat,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    module: Optional[str] = None,
    input_fh: Optional[str] = None,
    output_fh: Optional[str] = None,
    interp_method: Optional[str] = None,
    input_fmt: Optional[str] = None,
    time: Optional[str] = None,
    output_fmt: Optional[str] = None,
    uv_fmt: Optional[str] = None,
    delta_hour: Optional[str] = None,
    is_fill0: Optional[bool] = None,
    ntime: Optional[int] = None,
    is_min: Optional[bool] = None,
    index: Optional[str] = None,
    file_path: Optional[str] = None,
    file_time: Optional[str] = None,
    glon: Optional[str] = None,
    glat: Optional[str] = None,
) -> Dict[str, Any]:
    name = resolve_module(module)
    if name == "hourtomin":
        resolved_index = index.strip() if not _missing(index) else _opt_str("hourtomin", "index", str(PRESET["index"]))
        if resolved_index not in ("dtime", "time"):
            raise ValueError("index 只支持 dtime 或 time")
        return {
            "module": name,
            "ntime": _opt_int("hourtomin", "ntime", int(PRESET["ntime"])) if ntime is None else int(ntime),
            "is_min": _opt_bool("hourtomin", "is_min", bool(PRESET["is_min"])) if is_min is None else bool(is_min),
            "index": resolved_index,
        }
    if name == "read":
        return {
            "module": name,
            "file_path": _require("file_path", file_path, "read", "file_path"),
            "file_time": _require("file_time", file_time, "read", "file_time"),
            "glon": _require("glon", glon, "read", "glon"),
            "glat": _require("glat", glat, "read", "glat"),
        }
    interp = interp_method.strip() if not _missing(interp_method) else _opt_str(
        "timesplit", "interp_method", str(PRESET["interp_method"])
    )
    return {
        "module": name,
        "input_fh": _require("input_fh", input_fh, "timesplit", "input_fh"),
        "output_fh": _require("output_fh", output_fh, "timesplit", "output_fh"),
        "interp_method": interp,
        "input_fmt": _require("input_fmt", input_fmt, "timesplit", "input_fmt"),
        "time": _require("time", time, "timesplit", "time"),
        "output_fmt": _optional(output_fmt, "timesplit", "output_fmt"),
        "uv_fmt": _optional(uv_fmt, "timesplit", "uv_fmt"),
        "delta_hour": _optional(delta_hour, "timesplit", "delta_hour"),
        "is_fill0": _opt_bool("timesplit", "is_fill0", bool(PRESET["is_fill0"])) if is_fill0 is None else bool(is_fill0),
    }
