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

from grid_stat_merge import do_gs_merge, GridStatMergePlugin
from utils.util_env import get_resolved_paths, get_merge_params, set_main_ini


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


def process(
    grid_path: str = None,
    sta_path: str = None,
    output_path: str = None,
    terr_path: str = None,
    R: float = None,
    domain=None,
    b_use_heatflux_equation: bool = None,
    hf_eq_iter_nums: int = None,
    log_file: str = None,
    grid_type: str = None,
    sta_type: str = None,
    sta_val_col: str = None,
    sta_lon_col: str = None,
    sta_lat_col: str = None,
    config=None,
):
    """格站融合入口。``config`` 非空时本次调用改读该 ini，结束后恢复默认。"""
    kwargs = dict(
        grid_path=grid_path,
        sta_path=sta_path,
        output_path=output_path,
        terr_path=terr_path,
        R=R,
        domain=domain,
        b_use_heatflux_equation=b_use_heatflux_equation,
        hf_eq_iter_nums=hf_eq_iter_nums,
        log_file=log_file,
        grid_type=grid_type,
        sta_type=sta_type,
        sta_val_col=sta_val_col,
        sta_lon_col=sta_lon_col,
        sta_lat_col=sta_lat_col,
    )
    if not config:
        return _process_impl(**kwargs)
    set_main_ini(config)
    try:
        return _process_impl(**kwargs)
    finally:
        set_main_ini(None)


def _process_impl(
    grid_path: str = None,
    sta_path: str = None,
    output_path: str = None,
    terr_path: str = None,
    R: float = None,
    domain=None,
    b_use_heatflux_equation: bool = None,
    hf_eq_iter_nums: int = None,
    log_file: str = None,
    grid_type: str = None,
    sta_type: str = None,
    sta_val_col: str = None,
    sta_lon_col: str = None,
    sta_lat_col: str = None,
):
    """
    格站融合可调度入口。

    未传参数从 ``resource/conf.ini`` 读取。
    """
    paths = get_resolved_paths()
    params = get_merge_params()

    if log_file is not None:
        paths["log_file_template"] = log_file
    if grid_type is not None:
        params["grid_type"] = grid_type
    if sta_type is not None:
        params["sta_type"] = sta_type
    if sta_val_col is not None:
        params["sta_val_col"] = sta_val_col
    if sta_lon_col is not None:
        params["sta_lon_col"] = sta_lon_col
    if sta_lat_col is not None:
        params["sta_lat_col"] = sta_lat_col

    grid_path = grid_path or paths["grid_path"]
    sta_path = sta_path or paths["sta_path"]
    output_path = output_path or paths["output_path"]
    terr_path = terr_path if terr_path is not None else paths.get("terr_path", "")

    R = params["R"] if R is None else R
    domain = params["domain"] if domain is None else domain
    if b_use_heatflux_equation is None:
        b_use_heatflux_equation = params["b_use_heatflux_equation"]
    if hf_eq_iter_nums is None:
        hf_eq_iter_nums = params["hf_eq_iter_nums"]

    grd = _read_grid(grid_path, params["grid_type"])
    sta = _read_sta(sta_path, params["sta_type"])
    terr = _read_terr(terr_path) if terr_path else None

    # Micaps3 默认列多为 data0
    val_col = params["sta_val_col"]
    if val_col not in sta.columns and "data0" in sta.columns:
        val_col = "data0"

    grd_out = do_gs_merge(
        grd,
        sta,
        R=R,
        domain=domain,
        terr_mat=terr,
        b_use_heatflux_equation=b_use_heatflux_equation,
        hf_eq_iter_nums=hf_eq_iter_nums if b_use_heatflux_equation else None,
        sta_val_col=val_col,
        sta_lon_col=params["sta_lon_col"],
        sta_lat_col=params["sta_lat_col"],
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    meb.write_griddata_to_micaps4(grd_out, output_path, creat_dir=True)
    print("格站融合完成 →", output_path)
    return grd_out


if __name__ == "__main__":
    process()
