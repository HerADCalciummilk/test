# -*- coding: utf-8 -*-
"""
格点 → 格点 双线性插值。

在目标水平网格上，按源网格索引分数做双线性加权；
目标超出源网格时先插重叠区再 ``expand_to_contain_another_grid`` 填 ``outer_value``。
全球循环经度（源网格跨满 360°）按周期取模。

函数入口：``interp_gg_linear``
插件入口：``InterpGGLinearPlugin``（可调用，``plugin(grd, grid)``）

同源：仓库根 ``utils/interp_gg_pulgin.py``。
"""

from __future__ import annotations

import copy
from typing import Optional

import meteva
import numpy as np

from utils.base_plugin import BasePlugin


def interp_gg_linear(grd, grid, used_coords="xy", outer_value=None):
    """
    格点到格点双线性插值。

    输入
    ----
    grd : meteva 格点场
        源网格数据（含 member/level/time/dtime/lat/lon）。
    grid : meteva.base.grid
        目标网格定义（至少含 glon/glat；时间维等沿用 grd）。
    used_coords : str
        当前仅支持 ``"xy"``（水平插值）。
    outer_value : float, optional
        目标网格超出源网格时的外推填充值；越界时必须提供。

    输出
    ----
    grd_new : meteva 格点场 或 None
        插值到目标网格的结果；``grd is None`` 或越界未给 outer_value 时返回 None。
    """
    if grd is None:
        return None
    levels = grd["level"].values
    times = grd["time"].values
    dtimes = grd["dtime"].values
    members = grd["member"].values
    grid0 = meteva.base.basicdata.get_grid_of_data(grd)
    icycle = int(360 / grid0.dlon)
    iscycle = (grid0.dlon * grid0.nlon >= 360)
    if used_coords == "xy":
        is_out = False
        if not iscycle:
            if (grid.elon > grid0.elon or grid.slon < grid0.slon
                    or grid.elat > grid0.elat or grid.slat < grid0.slat):
                if outer_value is None:
                    print("当目标网格超出数据网格时，outer_value参数必须赋值")
                    return None
                is_out = True
        else:
            if (grid.elat > grid0.elat or grid.slat < grid0.slat):
                if outer_value is None:
                    print("当目标网格超出数据网格时，outer_value参数必须赋值")
                    return None
                is_out = True

        if is_out:
            grid_new0 = meteva.base.get_inner_grid(grid, grid0)
            grid_new = meteva.base.grid(
                grid_new0.glon, grid_new0.glat, grid0.gtime, grid0.dtimes, grid0.levels, grid0.members)
        else:
            grid_new = meteva.base.grid(
                grid.glon, grid.glat, grid0.gtime, grid0.dtimes, grid0.levels, grid0.members)
        grd_new = meteva.base.grid_data(grid_new)
        for i in range(len(levels)):
            for j in range(len(times)):
                for k in range(len(dtimes)):
                    for m in range(len(members)):
                        dat = grd.values[m, i, j, k, :, :]
                        x = ((np.arange(grid_new.nlon) * grid_new.dlon + grid_new.slon - grid0.slon) / grid0.dlon)
                        ig = x[:].astype(dtype="int16")
                        dx = x - ig
                        y = (np.arange(grid_new.nlat) * grid_new.dlat + grid_new.slat - grid0.slat) / grid0.dlat
                        jg = y[:].astype(dtype="int16")
                        dy = y - jg
                        ii, jj = np.meshgrid(ig, jg)
                        if iscycle:
                            ii1 = ii + 1
                            ii = ii % icycle
                            ii1 = ii1 % icycle
                        else:
                            ii1 = np.minimum(ii + 1, grid0.nlon - 1)
                        jj1 = np.minimum(jj + 1, grid0.nlat - 1)
                        ddx, ddy = np.meshgrid(dx, dy)
                        c00 = (1 - ddx) * (1 - ddy)
                        c01 = ddx * (1 - ddy)
                        c10 = (1 - ddx) * ddy
                        c11 = ddx * ddy
                        dat2 = (c00 * dat[jj, ii] + c10 * dat[jj1, ii]
                                + c01 * dat[jj, ii1] + c11 * dat[jj1, ii1])
                        grd_new.values[m, i, j, k, :, :] = dat2
        if is_out:
            grid_new1 = meteva.base.grid(
                grid.glon, grid.glat, grid0.gtime, grid0.dtimes, grid0.levels, grid0.members)
            grd_new = meteva.base.expand_to_contain_another_grid(
                grd_new, grid_new1, outer_value=outer_value)
    grd_new.attrs = copy.deepcopy(grd.attrs)
    return grd_new


class InterpGGLinearPlugin(BasePlugin):
    """
    可调用格点双线性插值插件。

    用法::

        plugin = InterpGGLinearPlugin(used_coords="xy", outer_value=0.0)
        grd_out = plugin(grd_in, target_grid)
        # 等价于
        grd_out = plugin.process(grd_in, target_grid)
    """

    def __init__(self, used_coords: str = "xy", outer_value: Optional[float] = None):
        self.used_coords = used_coords
        self.outer_value = outer_value

    def process(self, grd, grid, used_coords=None, outer_value=None):
        """
        输入: grd（源格点场）, grid（目标网格）
        输出: 插值后的格点场（或 None）
        """
        return interp_gg_linear(
            grd,
            grid,
            used_coords=self.used_coords if used_coords is None else used_coords,
            outer_value=self.outer_value if outer_value is None else outer_value,
        )
