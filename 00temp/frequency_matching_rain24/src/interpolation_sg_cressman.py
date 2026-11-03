# -- coding: utf-8 --
# @Time : 2026/10/26
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : interpolation_sg_cressman.py
# @Software: PyCharm
"""
站点→格点 Cressman 适配层。

由主程序 ``correct_tp_24h_nowcast.py`` 调用。
同名函数转发到子模块 ``interp_sg_cressman.src.interp_sg_cressman``
（影响半径由度换算为米）。

``correct_tp_24h.py`` 的 Cressman 在 ``interpolation.py`` 的 ``GressManInterpolation``。
``correct_tp_24h_nowcast.py`` 的双线性在 ``interpolation_gg_linear.py``。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import meteva.base as meb


def _ensure_interp_submodules_on_path() -> None:
    """将 ``interp_sg_cressman`` / ``interp_gg_linear`` 的根与 ``src`` 追加到 sys.path。"""
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    for name in ("interp_sg_cressman", "interp_gg_linear"):
        root = os.path.join(temp_root, name)
        src = os.path.join(root, "src")
        for p in (root, src):
            if os.path.isdir(p) and p not in sys.path:
                sys.path.append(p)


_ensure_interp_submodules_on_path()

from interp_gg_linear import interp_gg_linear  # noqa: E402
from interp_sg_cressman import interp_sg_cressman  # noqa: E402

# 经纬度度数 → 米（与 interp_sg_cressman 文档中 r_list 单位一致）
_DEG_TO_M = 111000.0


def _distance_limits_to_r_list(distance_limits):
    """旧接口影响半径（度）→ ``interp_sg_cressman`` 的 ``r_list``（米）。"""
    return [float(d) * _DEG_TO_M for d in distance_limits]


def _ensure_sta_dims(sta, grd):
    """保证站点表具备 interp_sg_cressman 所需的 time/dtime/level 列。"""
    out = sta.copy()
    grid_info = meb.basicdata.get_grid_of_data(grd)
    if "time" not in out.columns or out["time"].isna().all():
        try:
            t0 = np.asarray(grd["time"].values).ravel()[0]
        except Exception:
            t0 = grid_info.gtime[0] if getattr(grid_info, "gtime", None) else "2099010100"
        out["time"] = t0
    if "dtime" not in out.columns:
        out["dtime"] = 0
    if "level" not in out.columns:
        out["level"] = 0
    if "id" not in out.columns:
        out["id"] = np.arange(1, len(out) + 1)
    return out


def GressManInterpolation(sta, grd, distance_limits, num_limit=1.0, smooth=0.001, power_param=2.0, rain_limit=None):
    """
    站点→格点 Cressman（兼容旧签名）。

    Parameters
    ----------
    sta : 站点数据
    grd : 背景/目标格点场（取水平网格，并作为 background）
    distance_limits : sequence of float
        影响半径列表，单位为度（与历史调用一致）；内部换算为米后调用
        ``interp_sg_cressman``。
    num_limit / smooth / power_param :
        保留参数以兼容旧调用；共享 Cressman 模块不使用，忽略。
    rain_limit : float, optional
        若给出：插值结果小于等于该阈值的格点回退为背景场值（保持旧行为）。
    """
    del num_limit, smooth, power_param  # 兼容旧签名，共享模块无对应参数
    grid_info = meb.basicdata.get_grid_of_data(grd)
    grid = meb.basicdata.grid(grid_info.glon, grid_info.glat)
    sta1 = _ensure_sta_dims(sta, grd)
    r_list = _distance_limits_to_r_list(distance_limits)
    out = interp_sg_cressman(
        sta1,
        grid,
        r_list=r_list,
        background=grd,
        nearNum=100,
        outer_value=0.0,
    )
    if rain_limit is None:
        return out

    # 与旧实现一致：过小的订正值回退背景
    bg_aligned = interp_gg_linear(grd, grid, outer_value=0.0)
    if bg_aligned is None:
        return out
    out_vals = np.asarray(out.values, dtype=float).copy()
    bg_vals = np.asarray(bg_aligned.values, dtype=float)
    if out_vals.shape != bg_vals.shape:
        bg_vals = np.reshape(bg_vals, out_vals.shape)
    out_vals = np.where(out_vals <= rain_limit, bg_vals, out_vals)
    out_new = out.copy(deep=True)
    out_new.values[...] = out_vals
    return out_new
