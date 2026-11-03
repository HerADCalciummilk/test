# -*- coding: utf-8 -*-
"""
格点→格点双线性插值主入口（``src/runner.py``）。

读源格点 → ``interp_gg_linear`` → 写出 Micaps4。

调用::

    from runner import process
    process(grid_path=..., output_path=..., domain=[20, 50, 70, 140, 0.1, 0.1])

    python -m cli --grid=... --output=...
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

from interp_gg_linear import interp_gg_linear, InterpGGLinearPlugin
from utils.util_env import (
    build_glon_glat,
    get_linear_params,
    get_resolved_paths,
)


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
    grid_template_path: str = "",
    grid_template_type: str = "m4",
    glon=None,
    glat=None,
    domain=None,
):
    """
    目标网格优先级：
    1. 显式 glon/glat 或 domain
    2. grid_template_path 格点模板（仅取水平网格）
    """
    gg = build_glon_glat(
        glon if glon is not None else params.get("glon"),
        glat if glat is not None else params.get("glat"),
        domain if domain is not None else params.get("domain"),
    )
    if gg is not None:
        return meteva_base.basicdata.grid(gg[0], gg[1])

    if grid_template_path:
        tmpl = _read_griddata(grid_template_path, grid_template_type)
        g0 = _grid_of_data(tmpl)
        return meteva_base.basicdata.grid(g0.glon, g0.glat)

    raise ValueError(
        "无法确定目标网格：请在 ini/CLI 提供 glon+glat 或 domain，"
        "或提供 grid_template_path"
    )


def process(
    grid_path: str = None,
    output_path: str = None,
    grid_template_path: str = None,
    used_coords: str = None,
    outer_value=None,
    glon=None,
    glat=None,
    domain=None,
):
    """
    双线性插值可调度入口。未传参数从 ``resource/interp_gg_linear.ini`` 读取。
    """
    paths = get_resolved_paths()
    params = get_linear_params()

    grid_path = grid_path or paths["grid_path"]
    output_path = output_path or paths["output_path"]
    grid_template_path = (
        grid_template_path
        if grid_template_path is not None
        else paths.get("grid_template_path", "")
    )

    if used_coords is None:
        used_coords = params["used_coords"]
    if outer_value is None:
        outer_value = params["outer_value"]

    grd = _read_griddata(grid_path, params["grid_type"])
    grid = _resolve_target_grid(
        params,
        grid_template_path=grid_template_path,
        grid_template_type=params["grid_template_type"],
        glon=glon,
        glat=glat,
        domain=domain,
    )

    grd_out = interp_gg_linear(
        grd,
        grid,
        used_coords=used_coords,
        outer_value=outer_value,
    )
    if grd_out is None:
        raise RuntimeError(
            "插值未完成：目标网格超出源网格时必须提供 outer_value，"
            "或检查输入格点是否有效"
        )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    meb.write_griddata_to_micaps4(grd_out, output_path, creat_dir=True)
    print("格点双线性插值完成 →", output_path)
    return grd_out


if __name__ == "__main__":
    process()
