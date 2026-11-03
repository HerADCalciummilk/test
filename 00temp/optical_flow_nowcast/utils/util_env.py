# -*- coding: utf-8 -*-
"""从 ``resource/conf.ini`` 读取 CLI 参数。

取值优先级：显式参数 > ini 非空项 > ``PRESET``。
降水场、平流场路径和外推时次留空时直接报错。
命令行传入的路径保持原样；ini 里的相对路径按本包目录展开。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None

# kind, required, preset
_Field = Tuple[str, str, bool, Any]

FIELDS: Dict[str, Sequence[_Field]] = {
    "lk": (
        ("precip", "path", True, None),
        ("transform_method", "optstr", False, None),
        ("fd_method", "str", False, "shitomasi"),
        ("interp_method", "str", False, "idwinterp2d"),
        ("dense", "bool", False, True),
        ("nr_std_outlier", "int", False, 3),
        ("k_outlier", "int", False, 30),
        ("size_opening", "int", False, 3),
        ("decl_scale", "int", False, 20),
        ("verbose", "bool", False, False),
    ),
    "extrapolation": (
        ("precip", "path", True, None),
        ("velocity", "path", True, None),
        ("timesteps", "int", True, None),
        ("delta_min", "int", False, 10),
        ("extrap_method", "str", False, "semilagrangian"),
        ("measure_time", "bool", False, False),
    ),
    "sprog": (
        ("precip", "path", True, None),
        ("velocity", "path", True, None),
        ("timesteps", "int", True, None),
        ("delta_min", "int", False, 10),
        ("precip_thr", "float", False, -5.0),
        ("n_cascade_levels", "int", False, 6),
        ("extrap_method", "str", False, "semilagrangian"),
        ("decomp_method", "str", False, "fft"),
        ("bandpass_filter_method", "str", False, "gaussian"),
        ("ar_order", "int", False, 2),
        ("conditional", "bool", False, False),
        ("probmatching_method", "str", False, "cdf"),
        ("num_workers", "int", False, 1),
        ("fft_method", "str", False, "numpy"),
        ("domain", "str", False, "spatial"),
        ("measure_time", "bool", False, False),
    ),
    "linda": (
        ("precip", "path", True, None),
        ("velocity", "path", True, None),
        ("timesteps", "int", True, None),
        ("delta_min", "int", False, 10),
        ("add_perturbations", "bool", False, False),
        ("feature_method", "str", False, "blob"),
        ("max_num_features", "int", False, 25),
        ("ari_order", "int", False, 1),
        ("kernel_type", "str", False, "anisotropic"),
        ("localization_window_radius", "optfloat", False, None),
        ("errdist_window_radius", "optfloat", False, None),
        ("acf_window_radius", "optfloat", False, None),
        ("extrap_method", "str", False, "semilagrangian"),
        ("pert_thrs", "str", False, "0.5,1.0"),
        ("n_ens_members", "int", False, 10),
        ("vel_pert_method", "optstr", False, "bps"),
        ("kmperpixel", "optfloat", False, None),
        ("timestep", "optfloat", False, None),
        ("num_workers", "int", False, 1),
        ("seed", "optint", False, None),
        ("use_multiprocessing", "bool", False, False),
        ("measure_time", "bool", False, False),
        ("return_output", "bool", False, True),
    ),
    "steps": (
        ("precip", "path", True, None),
        ("velocity", "path", True, None),
        ("timesteps", "int", True, None),
        ("delta_min", "int", False, 10),
        ("n_ens_members", "int", False, 4),
        ("n_cascade_levels", "int", False, 6),
        ("precip_thr", "optfloat", False, None),
        ("kmperpixel", "optfloat", False, None),
        ("timestep", "optfloat", False, None),
        ("extrap_method", "str", False, "semilagrangian"),
        ("decomp_method", "str", False, "fft"),
        ("bandpass_filter_method", "str", False, "gaussian"),
        ("noise_method", "optstr", False, "nonparametric"),
        ("noise_stddev_adj", "optstr", False, None),
        ("ar_order", "int", False, 2),
        ("vel_pert_method", "optstr", False, None),
        ("conditional", "bool", False, False),
        ("probmatching_method", "str", False, "cdf"),
        ("mask_method", "optstr", False, None),
        ("seed", "optint", False, None),
        ("num_workers", "int", False, 1),
        ("fft_method", "str", False, "numpy"),
        ("domain", "str", False, "spatial"),
        ("measure_time", "bool", False, False),
        ("return_output", "bool", False, True),
    ),
}

MODULES = tuple(FIELDS)


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


def _as_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError(f"{key} 不是布尔值: {value}")


def _expand_paths(text: str, key: str) -> str:
    parts = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = (_PKG_ROOT / path).resolve()
        parts.append(str(path))
    if not parts:
        raise ValueError(f"{key} 未设置：命令行和 ini 都为空")
    return ",".join(parts)


def _coerce(kind: str, value: Any, key: str) -> Any:
    if kind == "path":
        text = str(value).strip()
        if not text:
            raise ValueError(f"{key} 未设置：命令行和 ini 都为空")
        return text
    if kind == "str":
        text = str(value).strip()
        if not text:
            raise ValueError(f"{key} 为空")
        return text
    if kind == "optstr":
        text = str(value).strip()
        return text or None
    if kind == "int":
        return int(value)
    if kind == "optint":
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return None
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "optfloat":
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return None
        return float(value)
    if kind == "bool":
        return _as_bool(value, key)
    raise ValueError(f"未知参数类型: {kind}")


def _missing(key: str) -> ValueError:
    return ValueError(f"{key} 未设置：命令行和 ini 都为空")


def resolve_args(module: str, *, config: Optional[str] = None, **explicit: Any) -> Dict[str, Any]:
    """按模块补齐参数。未出现在该模块字段表里的键会报错。

    ``config`` 给出时改读该 ini，返回前恢复默认文件。其余参数含义不变。
    """
    if config:
        set_main_ini(config)
    try:
        return _resolve_args(module, **explicit)
    finally:
        if config:
            set_main_ini(None)


def _resolve_args(module: str, **explicit: Any) -> Dict[str, Any]:
    if module not in FIELDS:
        raise ValueError(f"未知模块: {module}")
    spec = FIELDS[module]
    allowed = {item[0] for item in spec}
    unknown = sorted(set(explicit) - allowed)
    if unknown:
        raise ValueError(f"未知参数: {', '.join(unknown)}")
    resolved: Dict[str, Any] = {}
    for key, kind, required, preset in spec:
        given = explicit.get(key, None)
        if given is not None:
            resolved[key] = _coerce(kind, given, key)
            continue
        raw = _raw(module, key)
        if raw is None:
            if required:
                raise _missing(key)
            resolved[key] = preset
            continue
        if kind == "path":
            resolved[key] = _expand_paths(raw, key)
            continue
        resolved[key] = _coerce(kind, raw, key)
    return resolved
