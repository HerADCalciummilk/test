# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

MODES = ("lonlat-to-equal", "equal-to-lonlat")
_MODE_ALIASES = {
    "lonlat_to_equal": "lonlat-to-equal",
    "equal_to_lonlat": "equal-to-lonlat",
    "latlon-to-equal": "lonlat-to-equal",
    "equal-to-latlon": "equal-to-lonlat",
}

BACKENDS = ("cartopy", "iris")
_BACKEND_ALIASES = {
    "cartopy": "cartopy",
    "iris": "iris",
    "ir": "iris",
}

PRESET: Dict[str, Any] = {
    "mode": "lonlat-to-equal",
    "backend": "cartopy",
    "projection_extent": [83.0, 138.0, 12.0, 53.0],
    "secant_latitudes": [25.0, 47.0],
    "grid_distance": 1000.0,
    "lonlat_extent": [83.0, 138.0, 12.0, 53.0],
    "grid_spacing": 0.1,
    "regrid_mode": "bilinear",
    "extrapolation_mode": "nanmask",
}


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


def _opt_str(section: str, key: str, preset: str) -> str:
    raw = _raw(section, key)
    return preset if raw is None else raw


def _opt_float(section: str, key: str, preset: float) -> float:
    raw = _raw(section, key)
    return preset if raw is None else float(raw)


def _opt_float_list(section: str, key: str, preset: Sequence[float]) -> List[float]:
    raw = _raw(section, key)
    if raw is None:
        return [float(item) for item in preset]
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _as_float_list(value: Optional[str], fallback: List[float]) -> List[float]:
    if _missing(value):
        return list(fallback)
    return [float(item.strip()) for item in str(value).split(",") if item.strip()]


def _normalize_mode(mode: str) -> str:
    resolved = mode.strip().lower().replace("_", "-")
    resolved = _MODE_ALIASES.get(resolved, resolved)
    if resolved not in MODES:
        raise ValueError("mode 无效。可选 lonlat-to-equal、equal-to-lonlat")
    return resolved


def _normalize_backend(backend: str) -> str:
    resolved = backend.strip().lower()
    resolved = _BACKEND_ALIASES.get(resolved, resolved)
    if resolved not in BACKENDS:
        raise ValueError("backend 无效。可选 cartopy、iris（默认 cartopy）")
    return resolved


def resolve_args(
    mode: Optional[str] = None,
    backend: Optional[str] = None,
    projection_extent: Optional[str] = None,
    secant_latitudes: Optional[str] = None,
    grid_distance: Optional[float] = None,
    lonlat_extent: Optional[str] = None,
    grid_spacing: Optional[float] = None,
    regrid_mode: Optional[str] = None,
    extrapolation_mode: Optional[str] = None,
    config: Optional[str] = None,
) -> Dict[str, Any]:
    """补齐命令行参数。``config`` 给出时改读该 ini，返回前恢复默认文件。"""
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(
            mode=mode,
            backend=backend,
            projection_extent=projection_extent,
            secant_latitudes=secant_latitudes,
            grid_distance=grid_distance,
            lonlat_extent=lonlat_extent,
            grid_spacing=grid_spacing,
            regrid_mode=regrid_mode,
            extrapolation_mode=extrapolation_mode,
        )
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(
    mode: Optional[str] = None,
    backend: Optional[str] = None,
    projection_extent: Optional[str] = None,
    secant_latitudes: Optional[str] = None,
    grid_distance: Optional[float] = None,
    lonlat_extent: Optional[str] = None,
    grid_spacing: Optional[float] = None,
    regrid_mode: Optional[str] = None,
    extrapolation_mode: Optional[str] = None,
) -> Dict[str, Any]:
    raw_mode = mode.strip() if not _missing(mode) else _opt_str("cli", "mode", str(PRESET["mode"]))
    resolved_mode = _normalize_mode(raw_mode)
    raw_backend = (
        backend.strip()
        if not _missing(backend)
        else _opt_str("cli", "backend", str(PRESET["backend"]))
    )
    resolved_backend = _normalize_backend(raw_backend)
    extent = _as_float_list(
        projection_extent,
        _opt_float_list("lonlat_to_equal", "projection_extent", PRESET["projection_extent"]),
    )
    secant = _as_float_list(
        secant_latitudes,
        _opt_float_list("lonlat_to_equal", "secant_latitudes", PRESET["secant_latitudes"]),
    )
    lonlat = _as_float_list(
        lonlat_extent,
        _opt_float_list("equal_to_lonlat", "lonlat_extent", PRESET["lonlat_extent"]),
    )
    if len(extent) != 4:
        raise ValueError("projection_extent 须为 lonmin,lonmax,latmin,latmax 四个数")
    if len(secant) != 2:
        raise ValueError("secant_latitudes 须为两个纬度")
    if len(lonlat) != 4:
        raise ValueError("lonlat_extent 须为 lonmin,lonmax,latmin,latmax 四个数")
    regrid = regrid_mode.strip() if not _missing(regrid_mode) else _opt_str(
        "lonlat_to_equal", "regrid_mode", str(PRESET["regrid_mode"])
    )
    if regrid not in ("bilinear", "nearest"):
        raise ValueError("regrid_mode 只支持 bilinear 或 nearest")
    return {
        "mode": resolved_mode,
        "backend": resolved_backend,
        "projection_extent": extent,
        "secant_latitudes": secant,
        "grid_distance": float(
            _opt_float("lonlat_to_equal", "grid_distance", float(PRESET["grid_distance"]))
            if grid_distance is None
            else grid_distance
        ),
        "lonlat_extent": lonlat,
        "grid_spacing": float(
            _opt_float("equal_to_lonlat", "grid_spacing", float(PRESET["grid_spacing"]))
            if grid_spacing is None
            else grid_spacing
        ),
        "regrid_mode": regrid,
        "extrapolation_mode": (
            extrapolation_mode.strip()
            if not _missing(extrapolation_mode)
            else _opt_str(
                "lonlat_to_equal",
                "extrapolation_mode",
                str(PRESET["extrapolation_mode"]),
            )
        ),
    }
