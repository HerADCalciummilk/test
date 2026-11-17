# -*- coding: utf-8 -*-
"""格点→站点最近邻插值。

接口：``process(grd, sta)``。
算法参考 ``utils.interpolating.interp_gs_nearest``；
插值前经度预处理与 ``InterpGsLinear`` 对齐（``reset_lon_range`` /
``reset_global_griddata``）。
"""
from __future__ import annotations

import copy

import meteva_base as meb
import numpy as np
import pandas as pd

from gs_helpers import reset_global_griddata, reset_lon_range
from utils.base_plugin import PostProcessingPlugin


class InterpGsNearest(PostProcessingPlugin):
    """格点→站点最近邻插值。

    Parameters
    ----------
    used_coords :
        插值坐标；当前仅支持 ``"xy"``。
    """

    def __init__(self, used_coords: str = "xy"):
        if used_coords != "xy":
            raise ValueError('used_coords 当前仅支持 "xy"')
        self.used_coords = used_coords

    def process(self, grd, sta, used_coords=None):
        """格点→站点最近邻插值。

        Args:
            grd: 源格点场。
            sta: 目标站点表（至少含 lon/lat；id 等列保留）。
            used_coords: 覆盖构造参数；``None`` 用实例值。

        Returns:
            站点表；网格内无站点时为 ``None``。``attrs`` 继承自 ``grd``。
        """
        coords = self.used_coords if used_coords is None else used_coords
        if coords != "xy":
            raise ValueError('used_coords 当前仅支持 "xy"')
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

        sta1 = meb.sele.in_grid_xy(sta, grid)
        if len(sta1.index) == 0:
            return None
        ig = np.round((sta1.loc[:, "lon"].values - grid.slon) / grid.dlon).astype(
            dtype="int16"
        )
        jg = np.round((sta1.loc[:, "lat"].values - grid.slat) / grid.dlat).astype(
            dtype="int16"
        )
        sta_list = []
        for i in range(len(levels)):
            for j in range(len(times)):
                for k in range(len(dtimes)):
                    out = sta1.loc[:, ["time", "id", "lon", "lat"]].copy()
                    out.loc[:, "time"] = times[j]
                    out.loc[:, "dtime"] = dtimes[k]
                    out.loc[:, "level"] = levels[i]
                    for m in range(len(members)):
                        dat = grd.values[m, i, j, k, :, :]
                        out.loc[:, members[m]] = dat[jg, ig]
                    sta_list.append(out)
        sta_all = pd.concat(sta_list, axis=0)
        sta_all = sta_all.reindex(columns=column_list2)
        sta_all.attrs = copy.deepcopy(grd.attrs)
        return sta_all
