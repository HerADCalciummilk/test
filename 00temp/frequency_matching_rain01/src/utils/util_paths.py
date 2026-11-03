# -*- coding: utf-8 -*-
"""项目路径解析（与 mait_24h 的 util_env 风格一致）。"""
from __future__ import annotations

import os
from pathlib import Path

# 本文件位于 src/utils/，项目根为其上两级
_UTIL_DIR = Path(__file__).resolve().parent
REPO_ROOT = _UTIL_DIR.parent.parent
SRC_DIR = REPO_ROOT / "src"
RESOURCE_DIR = REPO_ROOT / "resource"
LOG_DIR = REPO_ROOT / "log"


def repo_root() -> Path:
    return REPO_ROOT


def resource_path(*parts: str) -> Path:
    return RESOURCE_DIR.joinpath(*parts)


def expand_repo_path(p: str | os.PathLike[str]) -> Path:
    path = Path(p).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()
