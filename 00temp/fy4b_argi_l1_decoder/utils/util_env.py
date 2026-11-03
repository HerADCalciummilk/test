# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
输入、输出和时间留空时直接报错，不猜测路径。
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
    "module": "batch",
    "resolution": 0.04,
    "lat_min": -60.0,
    "lat_max": 60.0,
    "lon_half_width": 75.0,
    "channels": "1-15",
    "resampling": "bilinear",
    "centers": "1050E,1330E",
    "overwrite": False,
    "recursive": False,
}

_MODULE_ALIASES = {"batch_latlon": "batch", "single_file": "single"}
_MODULES = ("batch", "single")


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


def _opt_str(section: str, key: str, preset: str) -> str:
    raw = _raw(section, key)
    return preset if raw is None else raw


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


def _pick_str(explicit: Optional[str], fallback: str) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    return fallback


def _require(name: str, explicit: Optional[str], section: str, key: str, *, path: bool = False) -> str:
    if not _missing(explicit):
        return str(explicit).strip()
    raw = _raw(section, key)
    if raw is None:
        raise ValueError(
            f"{name} 未指定。请传对应命令行参数，或在 resource/conf.ini 的 [{section}] 中填写 {key}"
        )
    return _expand(raw) if path else raw


def resolve_module(module: Optional[str] = None, config: Optional[str] = None) -> str:
    """选择 batch 或 single。显式参数优先，否则读 ``[cli] module``。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。
    """
    if config:
        set_main_ini(config)
    try:
        if _missing(module):
            module = _raw("cli", "module") or str(PRESET["module"])
        name = _MODULE_ALIASES.get(str(module).strip(), str(module).strip())
        if name not in _MODULES:
            raise ValueError("module 未指定或无效。请传 --module，可选 batch、single")
        return name
    finally:
        if config:
            set_main_ini(None)


def resolve_grid(
    resolution: Optional[float] = None,
    lat_min: Optional[float] = None,
    lat_max: Optional[float] = None,
    lon_half_width: Optional[float] = None,
    channels: Optional[str] = None,
    resampling: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_resolution = (
        _opt_float("grid", "resolution", float(PRESET["resolution"]))
        if resolution is None
        else float(resolution)
    )
    resolved_lat_min = _opt_float("grid", "lat_min", float(PRESET["lat_min"])) if lat_min is None else float(lat_min)
    resolved_lat_max = _opt_float("grid", "lat_max", float(PRESET["lat_max"])) if lat_max is None else float(lat_max)
    resolved_half = (
        _opt_float("grid", "lon_half_width", float(PRESET["lon_half_width"]))
        if lon_half_width is None
        else float(lon_half_width)
    )
    resolved_channels = _pick_str(channels, _opt_str("grid", "channels", str(PRESET["channels"])))
    resolved_resampling = _pick_str(resampling, _opt_str("grid", "resampling", str(PRESET["resampling"])))
    if resolved_resolution <= 0:
        raise ValueError("resolution 必须大于 0")
    if resolved_lat_min >= resolved_lat_max:
        raise ValueError("lat_min 必须小于 lat_max")
    if resolved_half <= 0:
        raise ValueError("lon_half_width 必须大于 0")
    if resolved_resampling not in ("nearest", "bilinear"):
        raise ValueError("resampling 只支持 nearest 或 bilinear")
    if _missing(resolved_channels):
        raise ValueError("channels 未指定")
    return {
        "resolution": resolved_resolution,
        "lat_min": resolved_lat_min,
        "lat_max": resolved_lat_max,
        "lon_half_width": resolved_half,
        "channels": resolved_channels,
        "resampling": resolved_resampling,
    }


def resolve_batch(
    input_root: Optional[str] = None,
    output_root: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    centers: Optional[str] = None,
    overwrite: Optional[bool] = None,
    recursive: Optional[bool] = None,
    config: Optional[str] = None,
    **grid: Any,
) -> Dict[str, Any]:
    """补齐批量解码参数。``config`` 给出时改读该 ini，返回前恢复默认文件。"""
    if config:
        set_main_ini(config)
    try:
        resolved = resolve_grid(**grid)
        resolved.update(
            {
                "input_root": _require("input_root", input_root, "batch", "input_root", path=True),
                "output_root": _require("output_root", output_root, "batch", "output_root", path=True),
                "start_time": _require("start_time", start_time, "batch", "start_time"),
                "end_time": _require("end_time", end_time, "batch", "end_time"),
                "centers": _pick_str(centers, _opt_str("batch", "centers", str(PRESET["centers"]))),
                "overwrite": (
                    _opt_bool("batch", "overwrite", bool(PRESET["overwrite"]))
                    if overwrite is None
                    else bool(overwrite)
                ),
                "recursive": (
                    _opt_bool("batch", "recursive", bool(PRESET["recursive"]))
                    if recursive is None
                    else bool(recursive)
                ),
            }
        )
        if _missing(resolved["centers"]):
            raise ValueError("centers 未指定")
        return resolved
    finally:
        if config:
            set_main_ini(None)


def resolve_single(
    input_hdf: Optional[str] = None,
    output_dir: Optional[str] = None,
    config: Optional[str] = None,
    **grid: Any,
) -> Dict[str, Any]:
    """补齐单文件解码参数。``config`` 给出时改读该 ini，返回前恢复默认文件。"""
    if config:
        set_main_ini(config)
    try:
        resolved = resolve_grid(**grid)
        resolved.update(
            {
                "input_hdf": _require("input_hdf", input_hdf, "single", "input_hdf", path=True),
                "output_dir": _require("output_dir", output_dir, "single", "output_dir", path=True),
            }
        )
        return resolved
    finally:
        if config:
            set_main_ini(None)
