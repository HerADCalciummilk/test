# -*- coding: utf-8 -*-
"""格点→站点双线性插值。

接口：``process(grd, sta)``。
算法参考 ``utils.interpolating.interp_gs_linear``
（含经度范围对齐与全球经度扩展；``used_coords`` 支持 ``xy`` / ``xyz`` / ``xydt``）。

``xydt`` 相对原实现的修复
---------------------------
原 ``interpolating.interp_gs_linear(..., used_coords=\"xydt\")`` 中：

1. ``coords_g`` 误建为 ``(ndtime, nlat, nlat, 3)``，reshape 用 ``nlat*nlat``，
   当 ``nlat != nlon`` 时与 ``dat_g``（``ndtime, nlat, nlon``）尺寸不一致即崩；
   即便相等，经度轴也按纬度长度铺开，坐标错误。
2. 用 ``LinearNDInterpolator`` 对规则网做三维散点插值，慢且与 ``xy``/``xyz``
   的可分离线性风格不一致。

此处改为与 ``xyz`` 同构：水平双线性 + ``dtime`` 维线性，保留站点自身 ``dtime``。
"""
from __future__ import annotations

import copy

import meteva_base as meb
import numpy as np
import pandas as pd

from gs_helpers import reset_global_griddata, reset_lon_range
from utils.base_plugin import PostProcessingPlugin


class InterpGsLinear(PostProcessingPlugin):
    """格点→站点双线性插值。

    Parameters
    ----------
    used_coords :
        ``"xy"`` 水平双线性；``"xyz"`` 再叠一层高度线性；
        ``"xydt"`` 水平双线性后再对站点 ``dtime`` 做线性（源场须至少 2 个时效）。
    """

    def __init__(self, used_coords: str = "xy"):
        if used_coords not in ("xy", "xyz", "xydt"):
            raise ValueError('used_coords 当前仅支持 "xy"、"xyz" 或 "xydt"')
        self.used_coords = used_coords

    @staticmethod
    def _axis_bracket(values, axis):
        """在单调轴 ``axis`` 上为 ``values`` 取左右下标及分数权重。"""
        axis = np.asarray(axis, dtype=float)
        values = np.asarray(values, dtype=float)
        if axis.size < 2:
            raise ValueError("插值轴长度须 >= 2")
        # 保证升序；降序时反转下标映射
        if axis[0] <= axis[-1]:
            ax = axis
            lo = np.searchsorted(ax, values, side="right") - 1
            lo = np.clip(lo, 0, ax.size - 2)
            hi = lo + 1
            w = (values - ax[lo]) / (ax[hi] - ax[lo] + 1e-30)
            return lo.astype("int16"), hi.astype("int16"), w
        ax = axis[::-1]
        lo_r = np.searchsorted(ax, values, side="right") - 1
        lo_r = np.clip(lo_r, 0, ax.size - 2)
        hi_r = lo_r + 1
        w = (values - ax[lo_r]) / (ax[hi_r] - ax[lo_r] + 1e-30)
        n = axis.size
        return (n - 1 - hi_r).astype("int16"), (n - 1 - lo_r).astype("int16"), w

    def process(self, grd, sta):
        """格点→站点双线性插值。

        Args:
            grd: 源格点场。
            sta: 目标站点表。

        Returns:
            站点表；``attrs`` 继承自 ``grd``。网格内无站点时返回 ``None``。
            ``xydt`` 且源 ``dtime`` 维长度为 1 时抛 ``ValueError``。
        """
        coords = self.used_coords
        if grd is None:
            return None

        grd = reset_lon_range(grd, sta)
        grd = reset_global_griddata(grd)

        levels = copy.deepcopy(grd["level"].values)
        times = copy.deepcopy(grd["time"].values)
        dtimes = copy.deepcopy(grd["dtime"].values)
        members = copy.deepcopy(grd["member"].values)
        column_list2 = ["level", "time", "dtime", "id", "lon", "lat"]
        column_list2.extend(list(members))
        grid = meb.get_grid_of_data(grd)

        if coords == "xy":
            sta1 = meb.sele.in_grid_xy(sta, grid)
            if len(sta1.index) == 0:
                return None
            ig = ((sta1["lon"].values - grid.slon) // grid.dlon).astype(dtype="int16")
            jg = ((sta1["lat"].values - grid.slat) // grid.dlat).astype(dtype="int16")
            dx = (sta1["lon"].values - grid.slon) / grid.dlon - ig
            dy = (sta1["lat"].values - grid.slat) / grid.dlat - jg
            c00 = (1 - dx) * (1 - dy)
            c01 = dx * (1 - dy)
            c10 = (1 - dx) * dy
            c11 = dx * dy
            ig1 = np.minimum(ig + 1, grid.nlon - 1)
            jg1 = np.minimum(jg + 1, grid.nlat - 1)
            sta_list = []
            for i in range(len(levels)):
                for j in range(len(times)):
                    for k in range(len(dtimes)):
                        out = sta1.loc[:, ["id", "lon", "lat"]].copy()
                        out["time"] = times[j]
                        out.loc[:, "dtime"] = dtimes[k]
                        out.loc[:, "level"] = levels[i]
                        for m in range(len(members)):
                            dat = grd.values[m, i, j, k, :, :]
                            dat_sta = (
                                c00 * dat[jg, ig]
                                + c01 * dat[jg, ig1]
                                + c10 * dat[jg1, ig]
                                + c11 * dat[jg1, ig1]
                            )
                            out.loc[:, members[m]] = dat_sta
                        sta_list.append(out)
            sta_all = pd.concat(sta_list, axis=0)
            sta_all = sta_all.reindex(columns=column_list2)
            sta_all.attrs = copy.deepcopy(grd.attrs)
            return sta_all

        if coords == "xyz":
            sta1 = meb.sele.in_grid_xyz(sta, grid)
            if len(sta1.index) == 0:
                return None
            lev_s = sta1["level"].values[:]
            lev_g = np.array(grid.levels)
            kg = meb.tool.math_tools.get_index(lev_s, grid.levels)
            kg1 = np.minimum(kg + 1, len(grid.levels) - 1)
            ig = ((sta1["lon"] - grid.slon) // grid.dlon).astype(dtype="int16")
            jg = ((sta1["lat"] - grid.slat) // grid.dlat).astype(dtype="int16")
            dx = (sta1["lon"] - grid.slon) / grid.dlon - ig
            dy = (sta1["lat"] - grid.slat) / grid.dlat - jg
            dz = (lev_s - lev_g[kg]) / (lev_g[kg1] - lev_g[kg] + 1e-30)
            c00 = (1 - dx) * (1 - dy)
            c01 = dx * (1 - dy)
            c10 = (1 - dx) * dy
            c11 = dx * dy
            ig1 = np.minimum(ig + 1, grid.nlon - 1)
            jg1 = np.minimum(jg + 1, grid.nlat - 1)
            sta_all = None
            for j in range(len(times)):
                for k in range(len(dtimes)):
                    out = sta1.loc[:, ["level", "id", "lon", "lat"]].copy()
                    out.loc[:, "time"] = times[j]
                    out.loc[:, "dtime"] = dtimes[k]
                    for m in range(len(members)):
                        dat = grd.values[m, :, j, k, :, :]
                        dat_sta = (
                            c00 * dat[kg, jg, ig]
                            + c01 * dat[kg, jg, ig1]
                            + c10 * dat[kg, jg1, ig]
                            + c11 * dat[kg, jg1, ig1]
                        ) * (1 - dz)
                        dat_sta = dat_sta + (
                            c00 * dat[kg1, jg, ig]
                            + c01 * dat[kg1, jg, ig1]
                            + c10 * dat[kg1, jg1, ig]
                            + c11 * dat[kg1, jg1, ig1]
                        ) * dz
                        out.loc[:, members[m]] = dat_sta
                    sta_all = meb.combine_join(sta_all, out)
            sta_all = sta_all.reindex(columns=column_list2)
            sta_all.attrs = copy.deepcopy(grd.attrs)
            return sta_all

        # xydt：水平双线性 + dtime 线性（站点保留自身 dtime）
        if len(grid.dtimes) < 2:
            raise ValueError("used_coords='xydt' 要求源场 dtime 维长度 >= 2")
        sta1 = meb.sele.in_grid_xy(sta, grid)
        if len(sta1.index) == 0:
            return None
        sta1 = meb.sele.between_dtime_range(sta1, grid.dtimes[0], grid.dtimes[-1])
        if sta1 is None or len(sta1.index) == 0:
            return None

        ig = ((sta1["lon"].values - grid.slon) // grid.dlon).astype(dtype="int16")
        jg = ((sta1["lat"].values - grid.slat) // grid.dlat).astype(dtype="int16")
        dx = (sta1["lon"].values - grid.slon) / grid.dlon - ig
        dy = (sta1["lat"].values - grid.slat) / grid.dlat - jg
        c00 = (1 - dx) * (1 - dy)
        c01 = dx * (1 - dy)
        c10 = (1 - dx) * dy
        c11 = dx * dy
        ig1 = np.minimum(ig + 1, grid.nlon - 1)
        jg1 = np.minimum(jg + 1, grid.nlat - 1)

        kd, kd1, wdt = self._axis_bracket(sta1["dtime"].values, grid.dtimes)

        sta_list = []
        for i in range(len(levels)):
            for j in range(len(times)):
                out = sta1.loc[:, ["dtime", "id", "lon", "lat"]].copy()
                out.loc[:, "time"] = times[j]
                out.loc[:, "level"] = levels[i]
                for m in range(len(members)):
                    # (dtime, lat, lon)
                    dat = grd.values[m, i, j, :, :, :]
                    v0 = (
                        c00 * dat[kd, jg, ig]
                        + c01 * dat[kd, jg, ig1]
                        + c10 * dat[kd, jg1, ig]
                        + c11 * dat[kd, jg1, ig1]
                    )
                    v1 = (
                        c00 * dat[kd1, jg, ig]
                        + c01 * dat[kd1, jg, ig1]
                        + c10 * dat[kd1, jg1, ig]
                        + c11 * dat[kd1, jg1, ig1]
                    )
                    out.loc[:, members[m]] = (1.0 - wdt) * v0 + wdt * v1
                sta_list.append(out)
        sta_all = pd.concat(sta_list, axis=0)
        sta_all = sta_all.reindex(columns=column_list2)
        sta_all.attrs = copy.deepcopy(grd.attrs)
        return sta_all
