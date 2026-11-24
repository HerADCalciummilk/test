# -*- coding: utf-8 -*-
"""
格站融合主入口（``src/runner.py``）。

读取格点 / 站点 → ``do_gs_merge`` → 写出 Micaps4。

调用::

    from runner import process
    process(grid_path=..., sta_path=..., output_path=...)

    python -m cli --grid=... --sta=... --output=...
    python src/runner.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths():
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed((str(_root), str(_src))):
        sys.path.insert(0, p)


_bootstrap_paths()

import meteva.base as meb


def _read_grid(path: str, grid_type: str):
    if not path or not os.path.exists(path):
        raise FileNotFoundError("格点文件不存在: %s" % path)
    gt = (grid_type or "m4").lower()
    if gt == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _read_sta(path: str, sta_type: str):
    if not path or not os.path.exists(path):
        raise FileNotFoundError("站点文件不存在: %s" % path)
    st = (sta_type or "m3").lower()
    if st == "nc":
        return meb.read_stadata_from_nc(path)
    return meb.read_stadata_from_micaps3(path)


def _read_terr(path: str):
    if not path:
        return None
    if not os.path.exists(path):
        raise FileNotFoundError("地形文件不存在: %s" % path)
    if path.lower().endswith(".nc"):
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def process(**kwargs):
    """兼容 ``from runner import process``。调度在 ``cli/grid_stat_merge_cli.py``。"""
    import importlib.util

    cli = Path(__file__).resolve().parents[1] / "cli" / "grid_stat_merge_cli.py"
    spec = importlib.util.spec_from_file_location("grid_stat_merge_cli", cli)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process(**kwargs)
