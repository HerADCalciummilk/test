# -*- coding: utf-8 -*-
"""统一 Cressman 插件：项目 km 核，可选频率匹配 aligned 再处理。

``process(..., reprocess=False)`` → ``interp_sg_cressman``（公里半径）
``process(..., reprocess=True)``  → 项目核 + 度制圆裁剪/融合等再处理
  （原 ``frequency_matching_rain24`` 的 ``cressman_project_innov``）
"""
from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import meteva.base as meb
import meteva_base
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

_KM_PER_DEG = float(getattr(meteva_base.basicdata.const, "ER", 6371.229)) * math.pi / 180.0


def _interp_sg_cressman(*args, **kwargs):
    from interp_sg_cressman import interp_sg_cressman as _fn

    return _fn(*args, **kwargs)
_SAFE_TIME = pd.Timestamp("2000-01-01 00:00:00")

# 再处理默认半径（度）；km 核默认见 CLI / conf.ini
DEFAULT_R_LIST_KM = (60000.0, 40000.0, 20000.0)
DEFAULT_R_LIST_DEG = (1.0, 0.8, 0.6, 0.4)


def _as2d(g):
    return np.asarray(g.values if hasattr(g, "values") else g.data, dtype=float).squeeze()


def _fix_grd_time(grd, t=_SAFE_TIME):
    out = grd.copy()
    try:
        n = int(out.sizes.get("time", len(np.atleast_1d(out.time.values))))
    except Exception:
        n = 1
    out = out.assign_coords(time=("time", [t] * max(n, 1)))
    return out


def _sanitize_sta_for_project(sta):
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


def _degree_disk_mask(lon, lat, sta_lon, sta_lat, r_deg):
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    sta_lon = np.atleast_1d(np.asarray(sta_lon, float))
    sta_lat = np.atleast_1d(np.asarray(sta_lat, float))
    lon2d, lat2d = np.meshgrid(lon, lat)
    if sta_lon.size == 1:
        return (lon2d - sta_lon[0]) ** 2 + (lat2d - sta_lat[0]) ** 2 <= float(r_deg) ** 2
    tree = cKDTree(np.column_stack([sta_lon, sta_lat]))
    pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
    dist, _ = tree.query(pts, k=1)
    return (dist <= float(r_deg)).reshape(lon2d.shape)


def _bg_idw_at_stations(cur, lon, lat, sta_lon, sta_lat, r_deg, dlon, smooth=0.001, power_param=2.0):
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    dlon = float(dlon)
    nlat, nlon = cur.shape
    r_deg = float(r_deg)
    r2 = r_deg * r_deg
    influence = max(int(r_deg / dlon), 0)
    start_lon, start_lat = float(lon[0]), float(lat[0])
    out = np.empty(len(sta_lon), dtype=float)
    for n, (x, y) in enumerate(zip(sta_lon, sta_lat)):
        i0 = int((x + 1e-5 - start_lon) / dlon)
        j0 = int((y + 1e-5 - start_lat) / dlon)
        i1, i2 = max(i0 - influence, 0), min(i0 + influence, nlon - 1)
        j1, j2 = max(j0 - influence, 0), min(j0 + influence, nlat - 1)
        sub = cur[j1 : j2 + 1, i1 : i2 + 1]
        dlon_v = lon[i1 : i2 + 1] - x
        dlat_v = lat[j1 : j2 + 1][:, np.newaxis] - y
        dist_sq = dlon_v ** 2 + dlat_v ** 2
        m = dist_sq <= r2
        if not np.any(m):
            out[n] = np.nan
            continue
        dist = np.sqrt(dist_sq[m])
        w = 1.0 / ((dist + smooth) ** power_param)
        ws = float(np.sum(w))
        out[n] = float(np.sum(w * sub[m]) / ws) if ws >= 1e-5 else np.nan
    return out


def _gressman_one_step(
    cur,
    lon,
    lat,
    sta_lon,
    sta_lat,
    sta_val,
    r_deg,
    dlon,
    num_limit=1.0,
    smooth=0.001,
    power_param=2.0,
    rain_limit=None,
):
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    dlon = float(dlon)
    nlat, nlon = cur.shape
    r_deg = float(r_deg)
    r2 = r_deg * r_deg
    influence = max(int(r_deg / dlon), 0)
    start_lon = float(lon[0])

    bg_sta = _bg_idw_at_stations(
        cur, lon, lat, sta_lon, sta_lat, r_deg, dlon, smooth, power_param
    )
    innov = np.asarray(sta_val, float) - np.where(np.isnan(bg_sta), np.asarray(sta_val, float), bg_sta)

    acc_w_val = np.zeros_like(cur)
    acc_w = np.zeros_like(cur)
    acc_n = np.zeros_like(cur)

    for n in range(len(sta_lon)):
        i0 = int((sta_lon[n] - start_lon) / dlon)
        j0 = int((sta_lat[n] - float(lat[0])) / dlon)
        i1, i2 = max(i0 - influence, 0), min(i0 + influence, nlon - 1)
        j1, j2 = max(j0 - influence, 0), min(j0 + influence, nlat - 1)
        if i1 > i2 or j1 > j2:
            continue
        dlon_v = lon[i1 : i2 + 1] - sta_lon[n]
        dlat_v = lat[j1 : j2 + 1][:, np.newaxis] - sta_lat[n]
        dist_sq = dlon_v ** 2 + dlat_v ** 2
        m = dist_sq <= r2
        if not np.any(m):
            continue
        dist = np.sqrt(dist_sq[m])
        w = 1.0 / ((dist + smooth) ** power_param)
        acc_w_val[j1 : j2 + 1, i1 : i2 + 1][m] += w * innov[n]
        acc_w[j1 : j2 + 1, i1 : i2 + 1][m] += w
        acc_n[j1 : j2 + 1, i1 : i2 + 1][m] += 1.0

    with np.errstate(divide="ignore", invalid="ignore"):
        blended = np.where(acc_w >= 1e-5, acc_w_val / acc_w + cur, cur)
    if rain_limit is not None:
        blended = np.where(blended <= float(rain_limit), cur, blended)
    return np.where((acc_w >= 1e-5) & (acc_n >= float(num_limit)), blended, cur)


def _station_anchor(cur, lon, lat, sta_lon, sta_lat, sta_val, radius_deg=0.35, strength=0.65):
    if strength <= 0 or len(sta_lon) == 0:
        return cur
    lon2d, lat2d = np.meshgrid(np.asarray(lon, float), np.asarray(lat, float))
    out = cur.copy()
    r2 = float(radius_deg) ** 2
    s = float(np.clip(strength, 0.0, 1.0))
    for x, y, v in zip(sta_lon, sta_lat, sta_val):
        d2 = (lon2d - x) ** 2 + (lat2d - y) ** 2
        w = np.clip(1.0 - d2 / r2, 0.0, 1.0) * s
        out = out * (1.0 - w) + float(v) * w
    return out


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
    """项目 km 核主扫 + 再处理，使结果接近度制 GressMan 形态。

    ``distance_limits`` 为**度**制半径列表。须提供含数据的背景格点 ``grd``。
    """
    grd_use = _fix_grd_time(grd)
    lon = np.asarray(grd_use.lon, float)
    lat = np.asarray(grd_use.lat, float)
    if hasattr(meb, "get_grid_of_data"):
        grid = meb.get_grid_of_data(grd_use)
    else:
        grid = meteva_base.basicdata.get_grid_of_data(grd_use)
    dlon = float(grid.dlon)
    bg0 = _as2d(grd_use).copy()
    cur = bg0.copy()
    sta_work = _sanitize_sta_for_project(sta)
    sta_lon = np.asarray(sta_work["lon"], float)
    sta_lat = np.asarray(sta_work["lat"], float)
    sta_val = np.asarray(sta_work["data0"], float)
    nsta = int(len(sta_work))
    if nsta == 0:
        return grd.copy()
    if nearNum is None:
        k_near = 8 if nsta <= 1 else min(100, nsta)
    else:
        k_near = max(1, min(int(nearNum), nsta))
    gain = float(innov_gain)
    scale = float(r_km_scale)
    n_extra = max(int(residual_passes), 0)
    n_polish = max(int(residual_polish_rounds), 1) if residual_degree_polish else 0
    blend = float(np.clip(degree_blend, 0.0, 1.0))

    def _one_sweep(radii, field):
        for r in radii:
            bg_sta = _bg_idw_at_stations(
                field, lon, lat, sta_lon, sta_lat, r, dlon, smooth=smooth, power_param=power_param
            )
            bg_sta = np.where(np.isnan(bg_sta), sta_val, bg_sta)
            innov_sta = sta_work.copy()
            innov_sta["data0"] = sta_val - bg_sta
            inc = _as2d(
                _interp_sg_cressman(
                    innov_sta,
                    grid,
                    r_list=[float(r) * _KM_PER_DEG * scale],
                    background=None,
                    nearNum=k_near,
                )
            )
            mask = _degree_disk_mask(lon, lat, sta_lon, sta_lat, r)
            if float(num_limit) > 1.0 and nsta > 0:
                tree = cKDTree(np.column_stack([sta_lon, sta_lat]))
                lon2d, lat2d = np.meshgrid(lon, lat)
                pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
                n_near = tree.query_ball_point(pts, r=float(r), return_length=True)
                n_near = np.asarray(n_near, dtype=float).reshape(field.shape)
                mask = mask & (n_near >= float(num_limit))
            new = field + np.where(mask, gain * inc, 0.0)
            if rain_limit is not None:
                new = np.where(new <= float(rain_limit), field, new)
            field = new
        return field

    cur = _one_sweep(distance_limits, cur)
    for _ in range(n_extra):
        small = list(distance_limits[-2:]) if len(distance_limits) >= 2 else list(distance_limits)
        cur = _one_sweep(small, cur)

    for _ in range(n_polish):
        for r in distance_limits:
            cur = _gressman_one_step(
                cur, lon, lat, sta_lon, sta_lat, sta_val, r, dlon,
                num_limit=num_limit, smooth=smooth, power_param=power_param, rain_limit=rain_limit,
            )

    if blend > 0.0:
        deg = bg0.copy()
        for r in distance_limits:
            deg = _gressman_one_step(
                deg, lon, lat, sta_lon, sta_lat, sta_val, r, dlon,
                num_limit=num_limit, smooth=smooth, power_param=power_param, rain_limit=rain_limit,
            )
        cur = (1.0 - blend) * cur + blend * deg

    if float(station_anchor_strength) > 0.0:
        cur = _station_anchor(
            cur, lon, lat, sta_lon, sta_lat, sta_val,
            radius_deg=station_anchor_radius,
            strength=station_anchor_strength,
        )
    if rain_limit is not None:
        cur = np.where(cur <= float(rain_limit), bg0, cur)

    out = grd.copy()
    out.data = [[[[cur]]]]
    return out


project_innov_wrap = cressman_project_innov


def cressman_innov_gressman_like(
    sta,
    grd,
    distance_limits,
    num_limit=1.0,
    smooth=0.001,
    power_param=2.0,
    rain_limit=None,
    nearNum=None,
):
    """封装内复刻度制 GressMan（不调项目 km 核）。``nearNum`` 忽略。"""
    _ = nearNum
    cur = _as2d(grd).copy()
    lon = np.asarray(grd.lon, float)
    lat = np.asarray(grd.lat, float)
    dlon = float(meteva_base.basicdata.get_grid_of_data(grd).dlon)
    sta_lon = np.asarray(sta["lon"], float)
    sta_lat = np.asarray(sta["lat"], float)
    sta_val = np.asarray(sta["data0"], float)
    if len(sta_lon) == 0:
        return grd.copy()
    for r in distance_limits:
        cur = _gressman_one_step(
            cur, lon, lat, sta_lon, sta_lat, sta_val, r, dlon,
            num_limit=num_limit, smooth=smooth, power_param=power_param, rain_limit=rain_limit,
        )
    out = grd.copy()
    out.data = [[[[cur]]]]
    return out


def cressman_innov_wrap(sta_lon, sta_lat, sta_val, bg, r_degs, nearNum=8):
    """lon/lat/val → 站表后走 ``cressman_project_innov``。"""
    return cressman_project_innov(
        _sanitize_sta_for_project(
            pd.DataFrame(
                {
                    "lon": list(np.atleast_1d(sta_lon)),
                    "lat": list(np.atleast_1d(sta_lat)),
                    "data0": list(np.atleast_1d(sta_val)),
                    "id": list(range(len(np.atleast_1d(sta_lon)))),
                }
            )
        ),
        bg,
        r_degs,
        nearNum=nearNum,
    )


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "on"):
        return True
    if text in ("0", "false", "no", "n", "off", ""):
        return False
    return bool(value)


def process(
    sta,
    grid=None,
    background=None,
    r_list: Optional[Sequence[float]] = None,
    nearNum: int = 100,
    outer_value=None,
    reprocess: Any = False,
    rain_limit=None,
    num_limit: float = 1.0,
    smooth: float = 0.001,
    power_param: float = 2.0,
    r_km_scale: float = 1.35,
    innov_gain: float = 1.0,
    residual_passes: int = 0,
    residual_degree_polish: bool = True,
    residual_polish_rounds: int = 1,
    degree_blend: float = 0.85,
    station_anchor_radius: float = 0.35,
    station_anchor_strength: float = 0.0,
    **kwargs: Any,
):
    """统一入口：``reprocess`` 决定路径（默认 ``False``）。

    - ``reprocess=False`` → ``interp_sg_cressman``（``r_list`` 为公里；须 ``grid``，
      或可由 ``background`` 取网格；``background`` 可作 km 核初值）
    - ``reprocess=True`` → ``cressman_project_innov``（``r_list`` 为度；须 ``background``）
    """
    _ = kwargs
    do_reprocess = _as_bool(reprocess, False)
    if not do_reprocess:
        if grid is None:
            if background is None:
                raise ValueError("reprocess=false 时须提供 grid，或提供 background 以取网格")
            g0 = (
                meb.get_grid_of_data(background)
                if hasattr(meb, "get_grid_of_data")
                else meteva_base.basicdata.get_grid_of_data(background)
            )
            grid = meteva_base.basicdata.grid(g0.glon, g0.glat)
        radii = list(r_list) if r_list is not None else list(DEFAULT_R_LIST_KM)
        return _interp_sg_cressman(
            sta,
            grid,
            r_list=radii,
            background=background,
            nearNum=int(nearNum),
            outer_value=outer_value,
        )

    if background is None:
        raise ValueError("reprocess=true 时必须提供 background 格点场")
    radii = list(r_list) if r_list is not None else list(DEFAULT_R_LIST_DEG)
    return cressman_project_innov(
        sta,
        background,
        radii,
        num_limit=float(num_limit),
        smooth=float(smooth),
        power_param=float(power_param),
        rain_limit=rain_limit,
        nearNum=nearNum,
        r_km_scale=float(r_km_scale),
        innov_gain=float(innov_gain),
        residual_passes=int(residual_passes),
        residual_degree_polish=_as_bool(residual_degree_polish, True),
        residual_polish_rounds=int(residual_polish_rounds),
        degree_blend=float(degree_blend),
        station_anchor_radius=float(station_anchor_radius),
        station_anchor_strength=float(station_anchor_strength),
    )


__all__ = [
    "process",
    "cressman_project_innov",
    "project_innov_wrap",
    "cressman_innov_gressman_like",
    "cressman_innov_wrap",
    "DEFAULT_R_LIST_KM",
    "DEFAULT_R_LIST_DEG",
]
