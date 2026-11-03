# -- coding: utf-8 --
# @Time : 2025/1/20 15:03
# @Author : 马劲松
# @Email : mjs1263153117@163.com
# @File : cal_optical_flow_nowcast.py
# @Software: PyCharm
"""
光流 / 半拉格朗日平流适配层。

由主程序 ``correct_tp_24h_nowcast.py`` 调用。

类名与调用签名与 ``cal_optical_flow.py`` 一致，
内部调用 ``optical_flow_nowcast`` 的 ``LK`` 与 ``Extrapolation``。
``correct_tp_24h.py`` 使用 ``cal_optical_flow.py``，不经过本文件。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import xarray as xr
import meteva.base as meb


def _ensure_optical_flow_nowcast_on_path() -> None:
    """将 ``00temp`` 追加到 sys.path，以便 ``import optical_flow_nowcast``（不抢占本包 utils）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    # .../frequency_matching_rain24/src → .../00temp
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    if os.path.isdir(os.path.join(temp_root, "optical_flow_nowcast")) and temp_root not in sys.path:
        sys.path.append(temp_root)


_ensure_optical_flow_nowcast_on_path()

from optical_flow_nowcast.src import Extrapolation, LK  # noqa: E402


def _as_list(grd):
    if isinstance(grd, xr.DataArray):
        return [grd]
    return list(grd)


def _stamp_time(grd: xr.DataArray, when: datetime) -> xr.DataArray:
    """按给定时刻重建 meb 格点场，供 LK 做等间隔时间序列检查。"""
    grid_info = meb.basicdata.get_grid_of_data(grd)
    glon = [grid_info.slon, grid_info.elon, grid_info.dlon]
    glat = [grid_info.slat, grid_info.elat, grid_info.dlat]
    grid = meb.grid(glon, glat, gtime=[when])
    vals = np.asarray(grd.values, dtype=float).squeeze()
    return meb.grid_data(grid, vals)


def _member_field(uv: xr.DataArray, name: str) -> np.ndarray:
    """从 LK 返回的 member=['u','v'] 场中取出二维数组。"""
    try:
        return np.asarray(uv.sel(member=name).values, dtype=float).squeeze()
    except Exception:
        members = list(np.asarray(uv["member"].values).ravel())
        idx = members.index(name) if name in members else (0 if name == "u" else 1)
        return np.asarray(uv.values, dtype=float).squeeze()[idx]


def _to_template(template: xr.DataArray, arr2d: np.ndarray) -> xr.DataArray:
    """把二维场写回与 template 同结构的格点 DataArray。"""
    out = template.copy(deep=True)
    arr2d = np.asarray(arr2d, dtype=float).squeeze()
    # meb griddata 通常为 (member, level, time, dtime, lat, lon)
    shape = list(out.values.shape)
    reshaped = arr2d.reshape(shape) if int(np.prod(shape)) == arr2d.size else None
    if reshaped is not None:
        out.values[...] = reshaped
    else:
        out.data = [[[[arr2d]]]]
    return out


def _build_velocity_griddata(u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
    """组装 Extrapolation 所需的 member=['u','v'] 速度场。"""
    grid_info = meb.basicdata.get_grid_of_data(u)
    glon = [grid_info.slon, grid_info.elon, grid_info.dlon]
    glat = [grid_info.slat, grid_info.elat, grid_info.dlat]
    try:
        gtime = [np.asarray(u["time"].values).ravel()[0]]
    except Exception:
        gtime = grid_info.gtime
    grid = meb.grid(glon, glat, gtime)
    grid.members = ["u", "v"]
    u2 = np.asarray(u.values, dtype=float).squeeze()
    v2 = np.asarray(v.values, dtype=float).squeeze()
    stacked = np.stack([u2, v2], axis=0)  # (2, nlat, nlon)
    stacked = stacked.reshape(2, 1, 1, 1, stacked.shape[-2], stacked.shape[-1])
    return meb.grid_data(grid, stacked)


class OpticalFlow:
    """兼容旧接口：内部用 ``LK`` 估计模式→实况位移场。"""

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
        """
        估计光流风场，结果写回 ``gd_output[0]=u``、``gd_output[1]=v``。

        ``min_window`` / ``rain_limit`` / ``delta_rain_limit`` / ``num_limit``
        保留以兼容旧调用；LK 算法不使用这些局地窗口参数。
        """
        del min_window, rain_limit, delta_rain_limit, num_limit
        before_list = _as_list(grd_before)
        next_list = _as_list(grd_next)
        if len(before_list) != len(next_list):
            raise ValueError("grd_before / grd_next length mismatch")

        lk = LK(verbose=False)
        t0 = datetime(2000, 1, 1, 0, 0, 0)
        dt = timedelta(hours=1)

        u_sum = None
        v_sum = None
        n_ok = 0
        for i, (b, a) in enumerate(zip(before_list, next_list)):
            pair = [
                _stamp_time(b, t0 + i * 2 * dt),
                _stamp_time(a, t0 + (i * 2 + 1) * dt),
            ]
            try:
                uv, _delta = lk.process(pair)
            except Exception:
                continue
            u2 = _member_field(uv, "u")
            v2 = _member_field(uv, "v")
            if u_sum is None:
                u_sum = np.zeros_like(u2, dtype=float)
                v_sum = np.zeros_like(v2, dtype=float)
            if u2.shape != u_sum.shape:
                continue
            u_sum += u2
            v_sum += v2
            n_ok += 1

        if n_ok == 0 or u_sum is None:
            gd_output[0] = gd_output[0] * 0
            gd_output[1] = gd_output[1] * 0
            return

        u_mean = u_sum / float(n_ok)
        v_mean = v_sum / float(n_ok)
        # LK 速度为像素位移；旧 Lagrangian 按「度」使用。
        # 换算：像素 → 度（× dlon / dlat），便于与 MultiValFormNewGridData 及
        # 本地半拉格朗日（若回退）一致；Extrapolation 路径会再转回像素。
        grid_info = meb.basicdata.get_grid_of_data(gd_output[0])
        u_deg = u_mean * float(grid_info.dlon)
        v_deg = v_mean * float(grid_info.dlat)
        gd_output[0] = _to_template(gd_output[0], u_deg)
        gd_output[1] = _to_template(gd_output[1], v_deg)


class Lagrangian:
    """兼容旧接口：内部用 ``Extrapolation`` 做半拉格朗日外推。"""

    @staticmethod
    def simple_semi_lagrangian_in_angle(
        gd_u_wnd: xr.DataArray,
        gd_v_wnd: xr.DataArray,
        gd_rain: xr.DataArray,
        delta_time,
    ):
        """
        沿光流场平流降水场一步。

        ``delta_time`` 为旧接口的时间因子（调用处固定为 1.0）；速度场已含一步位移，
        此处按 ``timesteps=1`` 外推。速度由度换回像素以匹配 Extrapolation/LK 约定。
        """
        grid_info = meb.basicdata.get_grid_of_data(gd_rain)
        # 输入 u/v 为「度/步」；Extrapolation 期望「像素/步」
        scale = float(delta_time) if delta_time is not None else 1.0
        u_arr = np.asarray(gd_u_wnd.values, dtype=float).squeeze() / float(grid_info.dlon) * scale
        v_arr = np.asarray(gd_v_wnd.values, dtype=float).squeeze() / float(grid_info.dlat) * scale
        u_px = _to_template(gd_u_wnd, u_arr)
        v_px = _to_template(gd_v_wnd, v_arr)
        velocity = _build_velocity_griddata(u_px, v_px)
        rain_timed = _stamp_time(gd_rain, datetime(2000, 1, 1, 0, 0, 0))
        # 需要至少 2 个时次才能过时间间隔检查；复制并错开 1h
        rain_prev = _stamp_time(gd_rain, datetime(2000, 1, 1, 0, 0, 0) - timedelta(hours=1))

        extrap = Extrapolation()
        try:
            result = extrap.process(
                [rain_prev, rain_timed],
                velocity,
                timesteps=1,
                delta_t=timedelta(hours=1),
            )
        except Exception:
            # 外推失败时回退：不做位移
            return gd_rain.copy(deep=True)

        out_vals = np.asarray(result.values, dtype=float).squeeze()
        # result 可能含 dtime 维：(ndtime, nlat, nlon) → 取第一步
        if out_vals.ndim == 3:
            out_vals = out_vals[0]
        return _to_template(gd_rain, out_vals)
