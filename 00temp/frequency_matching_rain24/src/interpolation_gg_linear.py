# -- coding: utf-8 --
# @Time : 2026/10/27
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : interpolation_gg_linear.py
# @Software: PyCharm
"""
双线性插值适配层。

由主程序 ``correct_tp_24h_nowcast.py`` 调用。函数名与 ``interpolation.py`` 一致：

- ``mesh_val``：格点→格点，转发子模块 ``interp_gg_linear.src.interp_gg_linear``
- ``bilinear_interp``：格点→站点。仓库没有单独的格点→站点算法包，
  转发 ``meteva.base.interp_gs_linear(..., reset_lon_range=False)``（其它项目算法已在用），
  越界站点填 ``dbUndef``，结果仍写在 ``data0``

``correct_tp_24h.py`` 的双线性仍在 ``interpolation.py``。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import meteva.base as meb


def _ensure_interp_gg_linear_on_path() -> None:
    """将 ``00temp/interp_gg_linear`` 的根与 ``src`` 追加到 sys.path（不抢占本包 utils）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    gg_root = os.path.join(temp_root, "interp_gg_linear")
    gg_src = os.path.join(gg_root, "src")
    for p in (gg_root, gg_src):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_ensure_interp_gg_linear_on_path()

from interp_gg_linear import interp_gg_linear  # noqa: E402


def _target_grid(inter_extend):
    """与 ``interpolation.mesh_val`` 相同的目标范围：``[slon, elon, slat, elat, res]``。"""
    slon, elon, slat, elat, res = inter_extend
    res = float(res)
    inter_lon = np.round(np.arange(slon, elon + 1e-05, res), 4)
    inter_lat = np.round(np.arange(slat, elat + 1e-05, res), 4)
    if len(inter_lon) == 1:
        inter_lon = np.append(inter_lon, float(inter_lon[0]) + res)
    if len(inter_lat) == 1:
        inter_lat = np.append(inter_lat, float(inter_lat[0]) + res)
    slon_g = float(inter_lon[0])
    slat_g = float(inter_lat[0])
    elon_g = slon_g + res * (len(inter_lon) - 1)
    elat_g = slat_g + res * (len(inter_lat) - 1)
    return meb.grid([slon_g, elon_g, res], [slat_g, elat_g, res])


def mesh_val(grd, inter_extend):
    """格点场重采样到 ``inter_extend`` 网格。越界填 0，与原 ``mesh_val`` 一致。"""
    grid = _target_grid(inter_extend)
    out = interp_gg_linear(grd, grid, outer_value=0.0)
    if out is None:
        raise ValueError("interp_gg_linear 未得到目标网格")
    return out


def bilinear_interp(grd, sta, dbUndef=0.0):
    """格点场插到站点。返回与 ``sta`` 同行的表，数值在 ``data0``。"""
    sampled = meb.interp_gs_linear(grd, sta, reset_lon_range=False)
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
