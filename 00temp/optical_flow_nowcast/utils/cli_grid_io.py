# -*- coding: utf-8 -*-
"""Load meb griddata paths for optical-flow CLI entry points."""
from __future__ import annotations

from pathlib import Path
from typing import List

import meteva_base as meb


_PKG_ROOT = Path(__file__).resolve().parents[1]


def split_path_list(path_text: str) -> List[str]:
    parts: List[str] = []
    for item in str(path_text).split(","):
        item = item.strip()
        if not item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = (_PKG_ROOT / path).resolve()
        parts.append(str(path))
    if not parts:
        raise ValueError("路径列表为空")
    return parts


def load_precip_griddata_list(path_text: str):

    return [meb.read_griddata_from_nc(path) for path in split_path_list(path_text)]


def load_velocity_griddata(path_text: str):

    path = split_path_list(path_text)[0]
    return meb.read_griddata_from_nc(path)
