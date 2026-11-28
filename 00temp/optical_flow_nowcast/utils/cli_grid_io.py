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


def save_grid_result(result, output):
    """把插件返回的格点写成 nc，后缀为 .m4 时写 MICAPS4。未给路径则不写。"""
    if output is None or not str(output).strip():
        return result
    grid = result[0] if isinstance(result, tuple) else result
    if grid is None:
        raise ValueError("已指定 output，但插件没有返回格点")
    path = Path(str(output).strip())
    suffix = path.suffix.lower()
    if suffix == ".m3":
        raise ValueError("光流结果是格点，请使用 .nc 或 .m4")
    if suffix == ".m4":
        meb.write_griddata_to_micaps4(grid, str(path), creat_dir=True)
    else:
        if suffix not in {".nc", ".nc4"}:
            path = Path(str(path) + ".nc")
        meb.write_griddata_to_nc(grid, str(path), creat_dir=True)
    print("已写出 %s" % path)
    return result
