# -*- coding: utf-8 -*-
"""
Cressman 站点→格点插值主入口（``src/runner.py``）。

读站点（可选背景/网格模板）→ ``interp_sg_cressman`` → 写出 Micaps4。

调用::

    from runner import process
    process(sta_path=..., output_path=..., r_list=[60000, 40000, 20000])

    python -m cli --sta=... --output=...
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
import meteva_base

from interp_sg_cressman import interp_sg_cressman, InterpSGCressmanPlugin
from utils.util_env import (
    build_glon_glat,
    get_cressman_params,
    get_resolved_paths,
)


def _read_sta(path: str, sta_type: str):
    if not path or not os.path.exists(path):
        raise FileNotFoundError("站点文件不存在: %s" % path)
    st = (sta_type or "m3").lower()
    if st == "nc":
        return meb.read_stadata_from_nc(path)
    return meb.read_stadata_from_micaps3(path)


def _read_griddata(path: str, gtype: str):
    if not path or not os.path.exists(path):
        raise FileNotFoundError("格点文件不存在: %s" % path)
    gt = (gtype or "m4").lower()
    if gt == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _grid_of_data(grd):
    if hasattr(meb, "get_grid_of_data"):
        return meb.get_grid_of_data(grd)
    return meteva_base.basicdata.get_grid_of_data(grd)


def _resolve_target_grid(
    params: dict,
    background=None,
    grid_template_path: str = "",
    grid_template_type: str = "m4",
    glon=None,
    glat=None,
    domain=None,
):
    """
    目标网格优先级：
    1. 显式 glon/glat 或 domain
    2. 背景场网格
    3. grid_template_path 格点模板
    """
    gg = build_glon_glat(
        glon if glon is not None else params.get("glon"),
        glat if glat is not None else params.get("glat"),
        domain if domain is not None else params.get("domain"),
    )
    if gg is not None:
        return meteva_base.basicdata.grid(gg[0], gg[1])

    if background is not None:
        g0 = _grid_of_data(background)
        return meteva_base.basicdata.grid(g0.glon, g0.glat)

    if grid_template_path:
        tmpl = _read_griddata(grid_template_path, grid_template_type)
        g0 = _grid_of_data(tmpl)
        return meteva_base.basicdata.grid(g0.glon, g0.glat)

    raise ValueError(
        "无法确定目标网格：请在 ini/CLI 提供 glon+glat 或 domain，"
        "或提供 background_path / grid_template_path"
    )


def process(
    sta_path: str = None,
    output_path: str = None,
    background_path: str = None,
    grid_template_path: str = None,
    r_list=None,
    nearNum: int = None,
    outer_value=None,
    glon=None,
    glat=None,
    domain=None,
):
    """
    Cressman 插值可调度入口。未传参数从 ``resource/interp_sg_cressman.ini`` 读取。
    """
    paths = get_resolved_paths()
    params = get_cressman_params()

    sta_path = sta_path or paths["sta_path"]
    output_path = output_path or paths["output_path"]
    background_path = (
        background_path if background_path is not None else paths.get("background_path", "")
    )
    grid_template_path = (
        grid_template_path
        if grid_template_path is not None
        else paths.get("grid_template_path", "")
    )

    if r_list is None:
        r_list = params["r_list"]
    if nearNum is None:
        nearNum = params["nearNum"]
    if outer_value is None:
        outer_value = params["outer_value"]

    sta = _read_sta(sta_path, params["sta_type"])
    background = None
    if background_path:
        background = _read_griddata(background_path, params["background_type"])

    grid = _resolve_target_grid(
        params,
        background=background,
        grid_template_path=grid_template_path,
        grid_template_type=params["grid_template_type"],
        glon=glon,
        glat=glat,
        domain=domain,
    )

    grd_out = interp_sg_cressman(
        sta,
        grid,
        r_list=r_list,
        background=background,
        nearNum=nearNum,
        outer_value=outer_value,
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    meb.write_griddata_to_micaps4(grd_out, output_path, creat_dir=True)
    print("Cressman 插值完成 →", output_path)
    return grd_out


if __name__ == "__main__":
    process()
