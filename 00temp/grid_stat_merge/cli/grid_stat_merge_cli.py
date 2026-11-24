# -*- coding: utf-8 -*-
"""格站融合调度。读格点与站点，调用 ``GridStatMergePlugin``，写出 Micaps4。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
for _p in (_SRC_DIR, _ROOT_DIR):
    sys.path.insert(0, _p)

from utils.merge_params import merge_params
from utils.util_env import get_merge_params, get_repo_root, get_resolved_paths, set_main_ini


def _abs_repo(path):
    if path is None:
        return ""
    text = str(path).strip()
    if not text:
        return ""
    raw = Path(text).expanduser()
    if raw.is_absolute():
        return os.path.normpath(str(raw))
    return os.path.normpath(str((Path(get_repo_root()) / raw).resolve()))


def _as_domain(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        parts = [float(item.strip()) for item in value.split(",") if item.strip()]
    else:
        parts = [float(item) for item in value]
    if len(parts) != 6:
        raise ValueError("domain 须为 6 个数：sou,nor,wst,est,dlon,dlat")
    return parts


@merge_params()
def process(
    grid_path=None,
    sta_path=None,
    output_path=None,
    terr_path=None,
    R: float = None,
    domain=None,
    b_use_heatflux_equation: bool = None,
    hf_eq_iter_nums: int = 20,
    log_file=None,
    grid_type: str = "m4",
    sta_type: str = "m3",
    sta_val_col: str = "data0",
    sta_lon_col: str = "lon",
    sta_lat_col: str = "lat",
    config=None,
):
    """格点与站点融合。``config`` 只换配置文件。``R`` 的 ini 键为小写 ``r``，缺省再取 200。"""
    if config:
        set_main_ini(config)
    try:
        paths = get_resolved_paths()
        params = get_merge_params()
    finally:
        if config:
            set_main_ini(None)

    _ = log_file
    import meteva.base as meb

    from grid_stat_merge import GridStatMergePlugin
    from runner import _read_grid, _read_sta, _read_terr

    grid_path = _abs_repo(grid_path) or paths["grid_path"]
    sta_path = _abs_repo(sta_path) or paths["sta_path"]
    output_path = _abs_repo(output_path) or paths["output_path"]
    terr_path = _abs_repo(terr_path) if terr_path else (paths.get("terr_path") or "")
    if R is None:
        R = params["R"]
    if domain is None:
        domain = params["domain"]
    else:
        domain = _as_domain(domain)
    if b_use_heatflux_equation is None:
        b_use_heatflux_equation = params["b_use_heatflux_equation"]
    if hf_eq_iter_nums is None:
        hf_eq_iter_nums = params["hf_eq_iter_nums"]

    grd = _read_grid(grid_path, grid_type)
    sta = _read_sta(sta_path, sta_type)
    terr = _read_terr(terr_path) if terr_path else None
    val_col = sta_val_col
    if val_col not in sta.columns and "data0" in sta.columns:
        val_col = "data0"

    grd_out = GridStatMergePlugin(
        R=R,
        domain=domain,
        terr_mat=terr,
        b_use_heatflux_equation=b_use_heatflux_equation,
        hf_eq_iter_nums=hf_eq_iter_nums if b_use_heatflux_equation else None,
        sta_val_col=val_col,
        sta_lon_col=sta_lon_col,
        sta_lat_col=sta_lat_col,
    ).process(grd, sta)

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    meb.write_griddata_to_micaps4(grd_out, output_path, creat_dir=True)
    print("格站融合完成 →", output_path)
    return grd_out
