# -*- coding: utf-8 -*-
"""新增算法：窗域 LSQR 估速 + 度制幂次 Cressman 铺 UV（rain24 原版 ``OpticalFlow``）。

与既有 ``LK`` / ``Extrapolation`` 并列独立，不改动旧实现。稀疏 UV 经同级新增的
``interp_sg_cressman.gressman_plugin.GressManInterpolation`` 铺密，再 ``mesh_val``。
类名 ``LsqrOpticalFlow``；兼容别名 ``OpticalFlow`` / ``WindowLsqr``。
"""
from __future__ import annotations

import datetime
import os
import sys
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr
import meteva_base as meb
from scipy.sparse.linalg import lsqr

from .base_plugin import PostProcessingPlugin


def _ensure_gressman_on_path() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    cress_root = os.path.join(temp_root, "interp_sg_cressman")
    cress_src = os.path.join(cress_root, "src")
    for p in (cress_src, cress_root):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_ensure_gressman_on_path()
from gressman_plugin import GressManInterpolation, mesh_val  # noqa: E402

GridLike = Union[xr.DataArray, Sequence[xr.DataArray]]


def _grid_of(grd: xr.DataArray):
    if hasattr(meb, "get_grid_of_data"):
        return meb.get_grid_of_data(grd)
    return meb.basicdata.get_grid_of_data(grd)


def _creat_m3_sta(lon_list, lat_list, data_list, rpt=None, dtime=0):
    """构造 Cressman 用站点表。不调用 ``set_stadata_coords``，避免 meteva_base/pandas 版本冲突。"""
    n = len(lon_list)
    if rpt is None:
        rpt = pd.Timestamp("2000-01-01")
    return pd.DataFrame(
        {
            "level": [0] * n,
            "time": [pd.Timestamp(rpt)] * n,
            "dtime": [dtime] * n,
            "id": list(range(n)),
            "lon": list(lon_list),
            "lat": list(lat_list),
            "data0": list(data_list),
        }
    )


def _central_gradient_y(grd: xr.DataArray, res: float) -> np.ndarray:
    grd_array = grd.data.squeeze().copy()
    array = grd.data.squeeze()
    grd_array[1:-1, 1:-1] = (array[1:-1, 2:] - array[1:-1, :-2]) / (2.0 * res)
    grd_array[1:-1, 0] = grd_array[1:-1, 1] + (grd_array[1:-1, 1] - grd_array[1:-1, 2])
    grd_array[1:-1, -1] = grd_array[1:-1, -2] + (grd_array[1:-1, -2] - grd_array[1:-1, -3])
    grd_array[0, :] = grd_array[1, :] + (grd_array[1, :] - grd_array[2, :])
    grd_array[-1, :] = grd_array[-2, :] + (grd_array[-2, :] - grd_array[-3, :])
    return grd_array


def _central_gradient_x(grd: xr.DataArray, res: float) -> np.ndarray:
    grd_array = grd.data.squeeze().copy()
    array = grd.data.squeeze()
    grd_array[1:-1, 1:-1] = (array[2:, 1:-1] - array[:-2, 1:-1]) / (2.0 * res)
    grd_array[1:-1, 0] = grd_array[1:-1, 1] + (grd_array[1:-1, 1] - grd_array[1:-1, 2])
    grd_array[1:-1, -1] = grd_array[1:-1, -2] + (grd_array[1:-1, -2] - grd_array[1:-1, -3])
    grd_array[0, :] = grd_array[1, :] + (grd_array[1, :] - grd_array[2, :])
    grd_array[-1, :] = grd_array[-2, :] + (grd_array[-2, :] - grd_array[-3, :])
    return grd_array


def _as_list(grd: GridLike) -> List[xr.DataArray]:
    if isinstance(grd, xr.DataArray):
        return [grd]
    return list(grd)


def _parse_min_windows(min_window) -> List[Tuple[float, float]]:
    """接受 ``[[5,5]]`` / ``(5,5)`` / ``\"5,5\"`` / ``\"5,5;2.5,2.5\"``。"""
    if min_window is None:
        return [(5.0, 5.0)]
    if isinstance(min_window, str):
        parts = [p.strip() for p in min_window.replace(";", "|").split("|") if p.strip()]
        out = []
        for part in parts:
            vals = [float(x) for x in part.split(",") if x.strip()]
            if len(vals) != 2:
                raise ValueError(f"min_window 需要 lon,lat 对，收到: {part!r}")
            out.append((vals[0], vals[1]))
        return out or [(5.0, 5.0)]
    if isinstance(min_window, (list, tuple)) and min_window and not isinstance(min_window[0], (list, tuple)):
        if len(min_window) != 2:
            raise ValueError(f"min_window 需要 lon,lat 对，收到: {min_window!r}")
        return [(float(min_window[0]), float(min_window[1]))]
    out = []
    for item in min_window:
        out.append((float(item[0]), float(item[1])))
    return out


def _estimate_one_window(
    grd_before: Sequence[xr.DataArray],
    grd_next: Sequence[xr.DataArray],
    min_window: Tuple[float, float],
    gd_output: List[xr.DataArray],
    rain_limit: float,
    delta_rain_limit: float,
    num_limit: int,
    lsqr_damp: float,
) -> None:
    grid_info = _grid_of(grd_before[0])
    delt_lon = grid_info.dlon
    delt_lat = grid_info.dlat
    lon_count, lat_count = grid_info.nlon, grid_info.nlat
    start_lon, end_lon = grid_info.slon, grid_info.elon
    start_lat, end_lat = grid_info.slat, grid_info.elat

    num_x = int(min_window[0] / delt_lon)
    num_y = int(min_window[1] / delt_lat)
    pdx = int(0.5 * num_x)
    pdy = int(0.5 * num_y)
    x_index = list(range(int(0.5 * num_x) + 1, lon_count, pdx))
    y_index = list(range(int(0.5 * num_y) + 1, lat_count, pdy))

    array1 = np.array([_central_gradient_x(gd, delt_lon) for gd in grd_before])
    array2 = np.array([_central_gradient_y(gd, delt_lon) for gd in grd_before])
    array3 = np.array([_central_gradient_x(gd, delt_lon) for gd in grd_next])
    array4 = np.array([_central_gradient_y(gd, delt_lon) for gd in grd_next])
    gd_gradient_x = (array1 + array3) * 0.5
    gd_gradient_y = (array2 + array4) * 0.5
    gd_delta = [
        grd_next[i].data.squeeze() - grd_before[i].data.squeeze() for i in range(len(grd_before))
    ]

    u_lon, u_lat, u_data = [], [], []
    v_lon, v_lat, v_data = [], [], []
    for j_index in y_index:
        for i_index in x_index:
            list3, list4, list5 = [], [], []
            for n in range(len(grd_before)):
                num3 = np.arange(j_index - pdy, j_index + pdy + 1)
                num4 = np.arange(i_index - pdx, i_index + pdx + 1)
                num3 = num3[(0 <= num3) & (num3 < lat_count)]
                num4 = num4[(0 <= num4) & (num4 < lon_count)]
                xx, yy = np.meshgrid(num3, num4, indexing="ij")
                gdq = gd_delta[n][xx, yy]
                gqb = grd_before[n].data.squeeze()[xx, yy]
                gqn = grd_next[n].data.squeeze()[xx, yy]
                condition = (np.abs(gdq) >= delta_rain_limit) & (
                    (gqb >= rain_limit) | (gqn >= rain_limit)
                )
                list3.extend(gd_gradient_x[n][xx[condition], yy[condition]])
                list4.extend(gd_gradient_y[n][xx[condition], yy[condition]])
                list5.extend(-1.0 * gdq[condition])
            if len(list5) >= num_limit:
                sparsematrix = np.vstack((list4, list3)).T
                result = lsqr(sparsematrix, list5, damp=lsqr_damp)
                if result[1]:
                    db_lon = start_lon + i_index * delt_lon
                    db_lat = start_lat + j_index * delt_lat
                    u_lon.append(db_lon)
                    u_lat.append(db_lat)
                    u_data.append(result[0][0])
                    v_lon.append(db_lon)
                    v_lat.append(db_lat)
                    v_data.append(result[0][1])

    if not u_data:
        return

    sd_input_data1 = _creat_m3_sta(u_lon, u_lat, u_data)
    sd_input_data2 = _creat_m3_sta(v_lon, v_lat, v_data)
    gd_background1 = mesh_val(
        gd_output[1], [start_lon, end_lon, start_lat, end_lat, min_window[1]]
    )
    gd_background2 = mesh_val(
        gd_output[0], [start_lon, end_lon, start_lat, end_lat, min_window[1]]
    )
    distance_limits = [4.0 * min_window[0], 2.0 * min_window[0], 1.0 * min_window[0]]
    grid_data2 = GressManInterpolation(sd_input_data1, gd_background2, distance_limits)
    grid_data3 = GressManInterpolation(sd_input_data2, gd_background1, distance_limits)
    gd_output[0] = mesh_val(grid_data2, [start_lon, end_lon, start_lat, end_lat, delt_lon])
    gd_output[1] = mesh_val(grid_data3, [start_lon, end_lon, start_lat, end_lat, delt_lon])


def estimate_optical_flow(
    grd_before: GridLike,
    grd_next: GridLike,
    min_window=None,
    gd_output=None,
    rain_limit: float = 0.1,
    delta_rain_limit: float = 0.1,
    num_limit: int = 100,
    lsqr_damp: float = 0.01,
) -> List[xr.DataArray]:
    """估计光流，写回 ``gd_output[0]=u``、``gd_output[1]=v``（度/步）。"""
    before = _as_list(grd_before)
    next_ = _as_list(grd_next)
    if len(before) != len(next_):
        raise ValueError(
            f"grd_before / grd_next 长度不一致: {len(before)} vs {len(next_)}"
        )
    if not before:
        raise ValueError("grd_before 为空")

    template = before[0]
    if gd_output is None:
        u0 = template.copy()
        v0 = template.copy()
        u0.data = np.zeros_like(template.data)
        v0.data = np.zeros_like(template.data)
        gd_output = [u0, v0]
    elif len(gd_output) < 2:
        raise ValueError("gd_output 需要 [u, v] 两个场")

    windows = _parse_min_windows(min_window)
    for win in windows:
        _estimate_one_window(
            before,
            next_,
            win,
            gd_output,
            rain_limit,
            delta_rain_limit,
            num_limit,
            lsqr_damp,
        )
    return gd_output


def _to_uv_member_grid(u_grd: xr.DataArray, v_grd: xr.DataArray) -> xr.DataArray:
    grid_info = _grid_of(u_grd)
    glon = [grid_info.slon, grid_info.elon, grid_info.dlon]
    glat = [grid_info.slat, grid_info.elat, grid_info.dlat]
    gtime = grid_info.gtime
    grid = meb.grid(glon, glat, gtime)
    grid.members = ["u", "v"]
    u = np.asarray(u_grd.data).squeeze()
    v = np.asarray(v_grd.data).squeeze()
    stacked = np.stack([u, v], axis=0).reshape(2, 1, 1, 1, u.shape[0], u.shape[1])
    return meb.grid_data(grid, stacked)


def forecast(
    grd_before: GridLike,
    grd_next: GridLike,
    min_window=None,
    rain_limit: float = 0.1,
    delta_rain_limit: float = 0.1,
    num_limit: int = 100,
    lsqr_damp: float = 0.01,
) -> xr.DataArray:
    """返回与 ``LK`` 同形的 member=[u,v] 速度场。"""
    u_v = estimate_optical_flow(
        grd_before,
        grd_next,
        min_window=min_window,
        rain_limit=rain_limit,
        delta_rain_limit=delta_rain_limit,
        num_limit=num_limit,
        lsqr_damp=lsqr_damp,
    )
    return _to_uv_member_grid(u_v[0], u_v[1])


class LsqrOpticalFlow(PostProcessingPlugin):
    """窗内 LSQR + 度制 Cressman UV，与 ``LK`` 并列的光流插件。"""

    def __init__(
        self,
        min_window=None,
        rain_limit: Optional[float] = None,
        delta_rain_limit: Optional[float] = None,
        num_limit: Optional[int] = None,
        lsqr_damp: Optional[float] = None,
        verbose: Optional[bool] = None,
    ) -> None:
        self.min_window = [[5.0, 5.0]] if min_window is None else min_window
        self.rain_limit = 0.1 if rain_limit is None else float(rain_limit)
        self.delta_rain_limit = 0.1 if delta_rain_limit is None else float(delta_rain_limit)
        self.num_limit = 100 if num_limit is None else int(num_limit)
        self.lsqr_damp = 0.01 if lsqr_damp is None else float(lsqr_damp)
        self.verbose = bool(verbose) if verbose is not None else False

    def get_optical_flow(
        self,
        grd_before,
        grd_next,
        min_window,
        gd_output,
        rain_limit=0.1,
        delta_rain_limit=0.1,
        num_limit=100,
    ):
        """兼容原 ``OpticalFlow.get_optical_flow``：就地写 ``gd_output``。"""
        estimate_optical_flow(
            grd_before,
            grd_next,
            min_window=min_window,
            gd_output=gd_output,
            rain_limit=rain_limit,
            delta_rain_limit=delta_rain_limit,
            num_limit=num_limit,
            lsqr_damp=self.lsqr_damp,
        )

    def process(
        self,
        grd_before: GridLike,
        grd_next: Optional[GridLike] = None,
    ) -> Tuple[xr.DataArray, Optional[datetime.timedelta]]:
        """估计光流速度场。

        Args:
            grd_before: 源场（如模式）；或仅传时间序列时作前若干帧。
            grd_next: 目标场（如实况）。省略且 ``grd_before`` 为长度≥2 的列表时，
                按相邻帧配对（类似 ``LK`` 时间序列用法）。

        Returns:
            ``(uv, delta_t)``：``uv`` 的 member 为 ``u``/``v``；无时间坐标时 ``delta_t`` 为 ``None``。
        """
        if grd_next is None:
            seq = _as_list(grd_before)
            if len(seq) < 2:
                raise ValueError("仅传一列场时至少需要 2 个时次")
            before = seq[:-1]
            next_ = seq[1:]
        else:
            before = _as_list(grd_before)
            next_ = _as_list(grd_next)

        if self.verbose:
            print(
                f"LsqrOpticalFlow: pairs={len(before)}, "
                f"min_window={self.min_window}, rain_limit={self.rain_limit}, "
                f"num_limit={self.num_limit}"
            )

        uv = forecast(
            before,
            next_,
            min_window=self.min_window,
            rain_limit=self.rain_limit,
            delta_rain_limit=self.delta_rain_limit,
            num_limit=self.num_limit,
            lsqr_damp=self.lsqr_damp,
        )

        delta_t = None
        try:
            t1 = pd.to_datetime(next_[-1].time).to_pydatetime()
            t0 = pd.to_datetime(before[-1].time).to_pydatetime()
            if isinstance(t1, (list, tuple, np.ndarray)):
                t1 = t1[0]
            if isinstance(t0, (list, tuple, np.ndarray)):
                t0 = t0[0]
            delta_t = t1 - t0
        except Exception:
            delta_t = None
        return uv, delta_t


WindowLsqr = LsqrOpticalFlow


class OpticalFlow:
    """rain24 兼容：``OpticalFlow.get_optical_flow`` 静态入口。"""

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
        LsqrOpticalFlow().get_optical_flow(
            grd_before,
            grd_next,
            min_window,
            gd_output,
            rain_limit=rain_limit,
            delta_rain_limit=delta_rain_limit,
            num_limit=num_limit,
        )


__all__ = [
    "LsqrOpticalFlow",
    "WindowLsqr",
    "OpticalFlow",
    "estimate_optical_flow",
    "forecast",
]
