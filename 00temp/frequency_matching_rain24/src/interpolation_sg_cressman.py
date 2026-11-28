# -- coding: utf-8 --
# @Time : 2026/10/26
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : interpolation_sg_cressman.py
# @Software: PyCharm
"""
站点→格点 Cressman 适配层。

由主程序 ``correct_tp_24h_nowcast.py`` 调用。
转发到 ``interpolation_station_grid`` 的 ``InterpSgCressman(reprocess=False)``
（影响半径由度换算为千米）；背景对齐用 ``interpolation_grid_grid.InterpGgLinear``。

``correct_tp_24h.py`` 的 Cressman 直接调用 ``interpolation_station_grid.InterpSg``。
``correct_tp_24h_nowcast.py`` 的双线性在 ``interpolation_gg_linear.py``。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import meteva.base as meb


def _ensure_interp_submodules_on_path() -> None:
    """将 ``interpolation_station_grid`` / ``interpolation_grid_grid`` 的根与 ``src`` 追加到 sys.path。"""
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    for name in ("interpolation_station_grid", "interpolation_grid_grid"):
        root = os.path.join(temp_root, name)
        src = os.path.join(root, "src")
        # 包根须先于 src，避免 src/utils 盖住包根 utils
        for p in (src, root):
            if os.path.isdir(p):
                if p in sys.path:
                    sys.path.remove(p)
                sys.path.insert(0, p)


_ensure_interp_submodules_on_path()

from interp_gg_linear_plugin import InterpGgLinear  # noqa: E402
from interp_sg_cressman_plugin import InterpSgCressman  # noqa: E402

# 经纬度 1 度对应的千米数（与 InterpSgCressman km 路径的距离单位一致：lon_lat_to_cartesian 输出千米）
_DEG_TO_KM = float(getattr(meb.basicdata.const, "ER", 6371.229)) * np.pi / 180.0


def _distance_limits_to_r_list(distance_limits):
    """旧接口影响半径（度）→ ``InterpSgCressman`` 的 ``r_list``（千米）。"""
    return [float(d) * _DEG_TO_KM for d in distance_limits]


def _ensure_sta_dims(sta, grd):
    """保证站点表具备 Cressman 所需的 time/dtime/level 列。"""
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
        影响半径列表，单位为度（与历史调用一致）；内部换算为千米后调用
        ``InterpSgCressman(reprocess=False)``。
    num_limit / smooth / power_param :
        保留参数以兼容旧调用；km 绝对值路径不使用，忽略。
    rain_limit : float, optional
        若给出：插值结果小于等于该阈值的格点回退为背景场值（保持旧行为）。
    """
    del num_limit, smooth, power_param  # 兼容旧签名，km 路径无对应参数
    grid_info = meb.basicdata.get_grid_of_data(grd)
    grid = meb.basicdata.grid(grid_info.glon, grid_info.glat)
    sta1 = _ensure_sta_dims(sta, grd)
    r_list = _distance_limits_to_r_list(distance_limits)
    out = InterpSgCressman(
        r_list=r_list,
        nearNum=100,
        outer_value=0.0,
        reprocess=False,
    ).process(sta1, grid=grid, background=grd)
    if rain_limit is None:
        return out

    # 与旧实现一致：过小的订正值回退背景
    bg_aligned = InterpGgLinear(outer_value=0.0).process(grd, grid)
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
