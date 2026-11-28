# -*- coding: utf-8 -*-
"""
Extrapolation / Lagrangian 再处理封装。

不改项目核源码，调整调用与后处理，使项目 ``Extrapolation.forecast`` 接近原版 ``Lagrangian``。
站点→格点 Cressman 统一由 ``interpolation_station_grid.InterpSg(method="cressman", ...)`` 提供；
``cressman_project_innov`` 是其旧签名薄封装（aligned 模式由 CLI 注入）。

aligned 估 UV 用原版 OpticalFlow；``OpticalFlowProject`` 仅可选对照。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import meteva_base as meb

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMP = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
_OF_ROOT = os.path.join(_TEMP, "optical_flow_nowcast")
_SG_SRC = os.path.join(_TEMP, "interpolation_station_grid", "src")
if os.path.isdir(_SG_SRC) and _SG_SRC not in sys.path:
    sys.path.append(_SG_SRC)
from interp_sg_plugin import InterpSg  # noqa: E402


def cressman_project_innov(
    sta,
    grd,
    distance_limits,
    num_limit=1.0,
    smooth=0.001,
    power_param=2.0,
    rain_limit=None,
    nearNum=None,
    r_km_scale=1.35,
    innov_gain=1.0,
    residual_passes=0,
    residual_degree_polish=True,
    residual_polish_rounds=1,
    degree_blend=0.85,
    station_anchor_radius=0.35,
    station_anchor_strength=0.0,
):
    """项目核再处理（aligned）：``InterpSg(method="cressman", reprocess=True)`` 的旧签名薄封装。

    ``distance_limits`` 为度（对应 ``r_list``）；须带背景场 ``grd``；站点为空时返回背景场副本。
    ``nearNum`` 为空时用 ``InterpSgCressman`` 的默认近邻数。
    """
    if len(sta) == 0:
        return grd.copy()
    extra = {} if nearNum is None else {"nearNum": nearNum}
    return InterpSg(
        method="cressman",
        r_list=list(distance_limits),
        reprocess=True,
        rain_limit=rain_limit,
        num_limit=num_limit,
        smooth=smooth,
        power_param=power_param,
        r_km_scale=r_km_scale,
        innov_gain=innov_gain,
        residual_passes=residual_passes,
        residual_degree_polish=residual_degree_polish,
        residual_polish_rounds=residual_polish_rounds,
        degree_blend=degree_blend,
        station_anchor_radius=station_anchor_radius,
        station_anchor_strength=station_anchor_strength,
        **extra,
    ).process(sta, background=grd)


def _import_optical_flow_src():
    """从 optical_flow_nowcast 导入 ``src`` 包中的外推与 LSQR 光流。

    顶层包名 ``src``、``utils`` 在多个子项目中重名，若直接 import 会被抢占或抢占本包。
    此处临时将 optical_flow_nowcast 根置于 sys.path 最前，导入前后保存并恢复 ``src``、
    ``utils`` 模块缓存与 sys.path，不影响本包后续导入。
    """
    def _pop(prefix):
        return {k: sys.modules.pop(k) for k in list(sys.modules) if k == prefix or k.startswith(prefix + ".")}

    saved_src, saved_utils = _pop("src"), _pop("utils")
    path_before = list(sys.path)
    try:
        while _OF_ROOT in sys.path:
            sys.path.remove(_OF_ROOT)
        sys.path.insert(0, _OF_ROOT)
        from src.extrapolation_plugin import forecast as extrap
        from src.lsqr_optical_flow_plugin import LsqrOpticalFlow as lsqr
    finally:
        sys.path[:] = path_before
        for prefix, saved in (("src", saved_src), ("utils", saved_utils)):
            for k in [k for k in sys.modules if (k == prefix or k.startswith(prefix + ".")) and k not in saved]:
                del sys.modules[k]
            sys.modules.update(saved)
    return extrap, lsqr


_OF_CACHE = {}


def _optical_flow_src():
    """按需加载（首次用到 aligned / OpticalFlowProject 时才导入 optical_flow_nowcast）。"""
    if not _OF_CACHE:
        extrap, lsqr = _import_optical_flow_src()
        _OF_CACHE["extrap"] = extrap
        _OF_CACHE["lsqr"] = lsqr()
    return _OF_CACHE


def _extrap_forecast(*args, **kwargs):
    return _optical_flow_src()["extrap"](*args, **kwargs)


# LsqrOpticalFlow/mesh_val → meteva grid(gtime=...) 对 1970-01-01 等会触发
# pandas date_range「exactly three must be specified」；统一换成安全时刻。
_SAFE_TIME = pd.Timestamp("2000-01-01 00:00:00")


def _as2d(g):
    """格点场 → 二维 float 数组。"""
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def _fix_grd_time(grd, t=_SAFE_TIME):
    """复制格点并把 time 维写成安全时刻（原地不改入参）。"""
    out = grd.copy()
    try:
        n = int(out.sizes.get("time", len(np.atleast_1d(out.time.values))))
    except Exception:
        n = 1
    out = out.assign_coords(time=("time", [t] * max(n, 1)))
    return out


def _fix_grd_list(grds, t=_SAFE_TIME):
    if isinstance(grds, (list, tuple)):
        return [_fix_grd_time(g, t) for g in grds]
    return _fix_grd_time(grds, t)


def _sanitize_sta_for_project(sta):
    """
    项目 LsqrOpticalFlow 友好的站点表：固定 time，避免 set_stadata_coords
    与异常 time 触发 pandas date_range 错误。
    """
    n = len(sta)
    ids = list(sta["id"]) if "id" in getattr(sta, "columns", []) else list(range(n))
    return pd.DataFrame(
        {
            "level": [0] * n,
            "time": [_SAFE_TIME] * n,
            "dtime": [0] * n,
            "id": ids,
            "lon": list(np.asarray(sta["lon"], float)),
            "lat": list(np.asarray(sta["lat"], float)),
            "data0": list(np.asarray(sta["data0"], float)),
        }
    )


class OpticalFlowProject:
    """
    项目 ``LsqrOpticalFlow`` 的静态入口，签名对齐原版 ``OpticalFlow.get_optical_flow``。

    调用前规范化格点 time，规避 rain24 产品里常见的 1970-01-01 触发 meteva date_range 崩溃。
    """

    @staticmethod
    def get_optical_flow(
        grd_before,
        grd_next,
        min_window,
        gd_output,
        rain_limit=0.1,
        delta_rain_limit=0.1,
        num_limit=100,
    ):
        before = _fix_grd_list(grd_before)
        next_ = _fix_grd_list(grd_next)
        # gd_output 就地写回：先规范化坐标再算，结果写回调用方原对象的 data
        out_u = _fix_grd_time(gd_output[0])
        out_v = _fix_grd_time(gd_output[1])
        _optical_flow_src()["lsqr"].get_optical_flow(
            before,
            next_,
            min_window,
            [out_u, out_v],
            rain_limit=rain_limit,
            delta_rain_limit=delta_rain_limit,
            num_limit=num_limit,
        )
        gd_output[0].data = out_u.data
        gd_output[1].data = out_v.data


def _clamp_bilinear(precip, u, v, lon, lat, dlon, dlat, dt=1.0):
    """
    复刻原版 Lagrangian 的后向双线性取样（含出界夹边）。

    原理：对每个格点 (λ,φ)，上游点 (λ−u·dt, φ−v·dt)；索引夹到 [0, n−2] 后
    做双线性。出界时权重可能 >1 或 <0，与原版一致（甚至可能出现负值）。

    用途：Extrapolation 出界填 nan 时，用本函数回填，使边界行为与原版一致。
    """
    precip = np.asarray(precip, dtype=float)
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    u = np.asarray(u, float) * dt
    v = np.asarray(v, float) * dt
    if u.ndim == 0:
        u = np.full_like(precip, float(u))
    if v.ndim == 0:
        v = np.full_like(precip, float(v))
    nlat, nlon = precip.shape
    lon2d, lat2d = np.meshgrid(lon, lat)
    lo, la = lon2d - u, lat2d - v
    i1 = np.clip(((lo - lon[0]) / dlon).astype(int), 0, nlon - 2)
    j1 = np.clip(((la - lat[0]) / dlat).astype(int), 0, nlat - 2)
    wl1, wl2 = (lon[i1 + 1] - lo) / dlon, (lo - lon[i1]) / dlon
    wa1, wa2 = (lat[j1 + 1] - la) / dlat, (la - lat[j1]) / dlat
    return (
        wl1 * (wa1 * precip[j1, i1] + wa2 * precip[j1 + 1, i1])
        + wl2 * (wa1 * precip[j1, i1 + 1] + wa2 * precip[j1 + 1, i1 + 1])
    )


def extrapolate_like_lagrangian(precip, u_deg, v_deg, lon, lat, dlon, dlat, delta_time=1.0):
    """
    用项目 Extrapolation 对齐原版 Lagrangian 搬雨结果。

    解决的问题
    ----------
    1. 单位：原版 UV 是度/步，项目是像素/步 → 此处做 u_px=u_deg/dlon 等换算。
    2. 切变风：项目默认 n_iter≥1 沿轨迹重采速度，与原版「当地风一步」不同，
       域内都会分叉 → 强制 ``n_iter=0``，与原版同为当地风、一步跳。
    3. 出界：项目常输出 nan，原版夹边双线性 → 对 nan/inf 用 ``_clamp_bilinear`` 回填。

    实现步骤
    --------
    1. 位移量（度）= UV(度/步)×delta_time，再 ÷格距 → 像素速度场 (2,nlat,nlon)。
    2. 调用项目 ``forecast(..., extrap_kwargs={n_iter:0})`` 外推 1 步。
    3. 有限格保留 Extrapolation；非有限格用原版夹边双线性从 ``precip`` 回填。

    Parameters
    ----------
    precip : ndarray (nlat, nlon)，搬雨前降水。
    u_deg, v_deg : 度/步，标量或与 precip 同形（东/北为正）。
    lon, lat : 一维经纬度坐标（与 precip 轴一致）。
    dlon, dlat : 格距（度）。
    delta_time : 与原版 Lagrangian 的 delta_time 同义，默认 1.0。

    Returns
    -------
    ndarray (nlat, nlon)，对齐原版 Lagrangian 的搬雨场。
    """
    precip = np.asarray(precip, float)
    u = np.asarray(u_deg, float) * delta_time
    v = np.asarray(v_deg, float) * delta_time
    if u.ndim == 0:
        u = np.full_like(precip, float(u))
    if v.ndim == 0:
        v = np.full_like(precip, float(v))
    # 度位移 → 像素/步；n_iter=0：不沿轨迹重采风
    raw = _extrap_forecast(
        precip,
        np.stack([u / dlon, v / dlat], 0),
        1,
        extrap_method="semilagrangian",
        extrap_kwargs={"n_iter": 0},
    )
    out = np.asarray(raw[0], float)
    # 出界 P1：nan → 原版夹边双线性
    fill = _clamp_bilinear(precip, u_deg, v_deg, lon, lat, dlon, dlat, dt=delta_time)
    return np.where(np.isfinite(out), out, fill)


class LagrangianAligned:
    """
    原版 ``Lagrangian.simple_semi_lagrangian_in_angle`` 的项目 Extrapolation 对齐版。

    签名与返回值与原版一致（DataArray in/out），内部走 ``extrapolate_like_lagrangian``
    （度→像素、n_iter=0、出界夹边回填）。
    """

    @staticmethod
    def simple_semi_lagrangian_in_angle(gd_u_wnd, gd_v_wnd, gd_rain, delta_time):
        precip = _as2d(gd_rain)
        u = _as2d(gd_u_wnd)
        v = _as2d(gd_v_wnd)
        lon = np.asarray(gd_rain.lon, float)
        lat = np.asarray(gd_rain.lat, float)
        grid_info = meb.basicdata.get_grid_of_data(gd_rain)
        moved = extrapolate_like_lagrangian(
            precip, u, v, lon, lat, grid_info.dlon, grid_info.dlat, delta_time=delta_time
        )
        out = gd_rain.copy()
        out.data = [[[[moved]]]]
        return out
