# -*- coding: utf-8 -*-
"""格点→站点双三次插值。

接口：``process(grd, sta)``。
算法参考 ``utils.interpolating.interp_gs_cubic``（水平 ``xy``）；
插值前经度预处理与 ``InterpGsLinear`` 对齐（``reset_lon_range`` /
``reset_global_griddata``）。
"""
from __future__ import annotations

import copy

import meteva_base as meb
import numpy as np

from gs_helpers import reset_global_griddata, reset_lon_range
from utils.base_plugin import PostProcessingPlugin


class InterpGsCubic(PostProcessingPlugin):
    """格点→站点双三次插值（水平 ``xy``）。"""

    @staticmethod
    def _cubic_f(n: int, dx: np.ndarray) -> np.ndarray:
        """三次卷积核权（与 ``interpolating.cubic_f`` 一致）。"""
        if n == -1:
            return -dx * (dx - 1) * (dx - 2) / 6
        if n == 0:
            return (dx + 1) * (dx - 1) * (dx - 2) / 2
        if n == 1:
            return -(dx + 1) * dx * (dx - 2) / 2
        return (dx + 1) * dx * (dx - 1) / 6

    def process(self, grd, sta):
        """格点→站点双三次插值。

        Args:
            grd: 源格点场。
            sta: 目标站点表。

        Returns:
            站点表；网格内无站点时为 ``None``。``attrs`` 继承自 ``grd``。
        """
        if grd is None:
            return None

        grd = reset_lon_range(grd, sta)
        grd = reset_global_griddata(grd)

        levels = grd["level"].values
        times = grd["time"].values
        dtimes = grd["dtime"].values
        members = grd["member"].values
        column_list2 = ["level", "time", "dtime", "id", "lon", "lat"]
        column_list2.extend(list(members))
        grid = meb.get_grid_of_data(grd)

        sta1 = meb.sele.in_grid_xy(sta, grid)
        if len(sta1.index) == 0:
            return None
        ig = ((sta1["lon"] - grid.slon) // grid.dlon).astype(dtype="int16")
        jg = ((sta1["lat"] - grid.slat) // grid.dlat).astype(dtype="int16")
        dx = (sta1["lon"] - grid.slon) / grid.dlon - ig
        dy = (sta1["lat"] - grid.slat) / grid.dlat - jg

        sta_all = None
        for i in range(len(levels)):
            for j in range(len(times)):
                for k in range(len(dtimes)):
                    out = sta1.loc[:, ["id", "lon", "lat"]].copy()
                    out.loc[:, "time"] = times[j]
                    out.loc[:, "dtime"] = dtimes[k]
                    out.loc[:, "level"] = levels[i]
                    for m in range(len(members)):
                        dat = grd.values[m, i, j, k, :, :]
                        total = np.zeros(len(out.index))
                        for p in range(-1, 3, 1):
                            iip = np.minimum(np.maximum(ig + p, 0), grid.nlon - 1)
                            fdx = self._cubic_f(p, dx)
                            for q in range(-1, 3, 1):
                                jjq = np.minimum(np.maximum(jg + q, 0), grid.nlat - 1)
                                fdy = self._cubic_f(q, dy)
                                total[:] += fdx * fdy * dat[jjq, iip]
                        out.loc[:, members[m]] = total
                    sta_all = meb.combine_join(sta_all, out)
        sta_all = sta_all.reindex(columns=column_list2)
        sta_all.attrs = copy.deepcopy(grd.attrs)
        return sta_all
