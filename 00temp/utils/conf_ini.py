# -*- coding: utf-8 -*-
"""读取子模块 ``resource/conf.ini``，或调用方传入的外部 ini。

只给入口函数补「仍为 None」的参数。已经传入的值保持不变，
因此默认空配置不会改算法结果。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

Caster = Union[str, Callable[[str], Any], None]


def conf_path(anchor_file: str, config: Optional[str] = None) -> Optional[Path]:
    """定位本次要读的 ini。

    ``config`` 为空时使用锚点文件所在包的 ``resource/conf.ini``。
    该文件不存在则返回 None。传入的路径不存在则抛出 FileNotFoundError。
    相对路径按包目录解析。
    """
    pkg = Path(anchor_file).resolve().parents[1]
    if config is None or not str(config).strip():
        default = pkg / "resource" / "conf.ini"
        return default if default.is_file() else None
    raw = Path(str(config).strip()).expanduser()
    chosen = raw if raw.is_absolute() else (pkg / raw)
    chosen = chosen.resolve()
    if not chosen.is_file():
        raise FileNotFoundError(f"配置文件不存在: {chosen}")
    return chosen


def load_process_ini(anchor_file: str, config: Optional[str] = None, section: str = "process") -> Dict[str, str]:
    """读取 ``[process]`` 中的非空项。没有该节时返回空字典。"""
    path = conf_path(anchor_file, config)
    if path is None:
        return {}
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    if not parser.has_section(section):
        return {}
    out: Dict[str, str] = {}
    for key, value in parser.items(section):
        text = value.strip()
        if text:
            out[key] = text
    return out


def _cast(raw: str, caster: Caster) -> Any:
    if caster is None or caster == "str":
        return raw
    if callable(caster):
        return caster(raw)
    if caster == "int":
        return int(raw)
    if caster == "float":
        return float(raw)
    if caster == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if caster == "float_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return float(parts[0])
        return [float(item) for item in parts]
    if caster == "str_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return parts[0]
        return parts
    if caster == "int_list":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        if len(parts) == 1:
            return int(parts[0])
        return [int(item) for item in parts]
    if caster == "int_tuple":
        parts = [item.strip() for item in raw.split(",") if item.strip()]
        return tuple(int(item) for item in parts)
    return raw


def overlay_none(
    anchor_file: str,
    config: Optional[str],
    values: Dict[str, Any],
) -> Dict[str, Any]:
    """用 ini 填补仍为 None 的参数。

    ``values`` 的值可以是当前参数，或 ``(当前值, 转换名)``。
    当前值不是 None 时保持原样。
    """
    ini = load_process_ini(anchor_file, config)
    out: Dict[str, Any] = {}
    for key, spec in values.items():
        if isinstance(spec, tuple):
            current, caster = spec
        else:
            current, caster = spec, None
        if current is None and key in ini:
            out[key] = _cast(ini[key], caster)
        else:
            out[key] = current
    return out
