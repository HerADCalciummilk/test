# -*- coding: utf-8 -*-
"""格点→格点重采样与格点→站点双线性插值适配层。

复用两个正式插值包（站点→格点 Cressman 请直接调用 ``interpolation_station_grid.InterpSg``）：
- ``mesh_val`` → ``interpolation_grid_grid.InterpGgLinear(outer_value=0.0)``
- ``bilinear_interp`` → ``interpolation_grid_station.InterpGsLinear(used_coords="xy")``
"""
from __future__ import annotations

import os
import sys

import meteva_base as meb
import numpy as np


def _ensure_interp_packages_on_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    paths = [
        temp_root,
        os.path.join(temp_root, "interpolation_grid_grid", "src"),
        os.path.join(temp_root, "interpolation_grid_station", "src"),
    ]
    for p in paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_ensure_interp_packages_on_path()

from interp_gg_linear_plugin import InterpGgLinear  # noqa: E402
from interp_gs_linear_plugin import InterpGsLinear  # noqa: E402


def _target_grid(inter_extend):
    slon, elon, slat, elat, res = inter_extend
    res = float(res)
    inter_lon = np.round(np.arange(slon, elon + 1e-5, res), 4)
    inter_lat = np.round(np.arange(slat, elat + 1e-5, res), 4)
    if len(inter_lon) == 1:
        inter_lon = np.append(inter_lon, float(inter_lon[0]) + res)
    if len(inter_lat) == 1:
        inter_lat = np.append(inter_lat, float(inter_lat[0]) + res)
    slon_g = float(inter_lon[0])
    slat_g = float(inter_lat[0])
    elon_g = slon_g + res * (len(inter_lon) - 1)
    elat_g = slat_g + res * (len(inter_lat) - 1)
    return meb.basicdata.grid([slon_g, elon_g, res], [slat_g, elat_g, res])


def mesh_val(grd, inter_extend):
    """格点场双线性重采样到 ``inter_extend`` 网格（越界填 0，保留 ``member`` 坐标）。"""
    grid = _target_grid(inter_extend)
    out = InterpGgLinear(outer_value=0.0).process(grd, grid)
    if out is None:
        raise ValueError("InterpGgLinear 未得到目标网格")
    if "member" in grd.coords and "member" in out.coords:
        out["member"] = grd.member
    return out


def bilinear_interp(grd, sta, dbUndef=0.0):
    """格点场水平双线性插值到站点；越界或 NaN 填 ``dbUndef``，写入 ``data0``。"""
    sampled = InterpGsLinear(used_coords="xy").process(grd, sta)
    out = sta.copy()
    vals = np.full(len(out), float(dbUndef), dtype=float)
    if sampled is not None and len(sampled) > 0:
        value_col = "data0" if "data0" in sampled.columns else sampled.columns[-1]
        indexer = out.index.get_indexer(sampled.index)
        ok = indexer >= 0
        src = np.asarray(sampled[value_col], dtype=float)
        vals[indexer[ok]] = src[ok]
        vals = np.where(np.isnan(vals), float(dbUndef), vals)
    out["data0"] = vals
    return out


__all__ = ["bilinear_interp", "mesh_val"]
