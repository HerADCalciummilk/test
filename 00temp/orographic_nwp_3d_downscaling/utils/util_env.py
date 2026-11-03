# -*- coding: utf-8 -*-
"""地形降尺度命令行配置路径。

算法参数仍由 ``--para-file``（位于 ``--work-dir``）读取。
``--config`` 传入时，``set_main_ini`` 把该文件设为本次参数 ini。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Optional

_PKG_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INI = _PKG_ROOT / "resource" / "conf.ini"
_INI_PATH = _DEFAULT_INI
_CACHE: Optional[configparser.ConfigParser] = None


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
    """读取当前生效的 ini。缺文件时抛出 ``FileNotFoundError``。"""
    global _CACHE
    if _CACHE is None:
        if not _INI_PATH.is_file():
            raise FileNotFoundError(f"配置文件不存在: {_INI_PATH}")
        parser = configparser.ConfigParser()
        parser.read(_INI_PATH, encoding="utf-8")
        _CACHE = parser
    return _CACHE
