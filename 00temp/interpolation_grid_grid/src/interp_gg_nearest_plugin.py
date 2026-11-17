# -*- coding: utf-8 -*-
"""格点→格点最近邻插值。

接口：``process(grd, grid)``。
算法参考 ``utils.interpolating.interp_gg_nearest``；
越界判定与 ``InterpGgLinear`` 对齐（全球循环场仍检查纬度越界）。
依赖 ``meteva_base``，不直接调用库内 ``interp_gg_nearest``。

算法要点
--------
1. 将目标格点映射到源网格索引，四舍五入取最近格点赋值。
2. 源场经度跨满 360°（``iscycle``）时：纬度越界仍须 ``outer_value``；经度下标取模。
3. 非循环场经纬任一越界：先插重叠区，再 ``expand_to_contain_another_grid`` 填外区。
4. member / level / time / dtime 沿用源场；水平网格取自目标 ``grid``。
"""
from __future__ import annotations

import copy
from typing import Optional

import meteva_base as meb
import numpy as np

from utils.base_plugin import PostProcessingPlugin


class InterpGgNearest(PostProcessingPlugin):
    """格点→格点最近邻插值。

    Parameters
    ----------
    used_coords :
        插值坐标；当前仅支持 "xy"（水平）。
    outer_value :
        目标超出源网格时的填充值；越界时必须提供，否则返回 ``None``。
    """

    def __init__(
        self,
        used_coords: str = "xy",
        outer_value: Optional[float] = None,
    ):
        if used_coords != "xy":
            raise ValueError('used_coords 当前仅支持 "xy"')
        self.used_coords = used_coords
        self.outer_value = outer_value

    def process(self, grd, grid, used_coords=None, outer_value=None):
        """格点→格点最近邻插值。

        Args:
            grd: 源格点场。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。
            used_coords: 覆盖构造参数；``None`` 用实例值。
            outer_value: 覆盖构造参数；``None`` 用实例值。

        Returns:
            插值到目标网格的格点场；``grd is None`` 或越界未给 ``outer_value`` 时为 ``None``。
        """
        coords = self.used_coords if used_coords is None else used_coords
        fill = self.outer_value if outer_value is None else outer_value
        if coords != "xy":
            raise ValueError('used_coords 当前仅支持 "xy"')
        if grd is None:
            return None

        levels = grd["level"].values
        times = grd["time"].values
        dtimes = grd["dtime"].values
        members = grd["member"].values
        grid0 = meb.basicdata.get_grid_of_data(grd)
        icycle = int(360 / grid0.dlon)
        iscycle = grid0.dlon * grid0.nlon >= 360

        is_out = False
        if not iscycle:
            if (
                grid.elon > grid0.elon
                or grid.slon < grid0.slon
                or grid.elat > grid0.elat
                or grid.slat < grid0.slat
            ):
                if fill is None:
                    print("当目标网格超出数据网格时，outer_value参数必须赋值")
                    return None
                is_out = True
        else:
            if grid.elat > grid0.elat or grid.slat < grid0.slat:
                if fill is None:
                    print("当目标网格超出数据网格时，outer_value参数必须赋值")
                    return None
                is_out = True

        if is_out:
            grid_new0 = meb.get_inner_grid(grid, grid0)
            grid_new = meb.grid(
                grid_new0.glon,
                grid_new0.glat,
                grid0.gtime,
                grid0.dtimes,
                grid0.levels,
                grid0.members,
            )
        else:
            grid_new = meb.grid(
                grid.glon,
                grid.glat,
                grid0.gtime,
                grid0.dtimes,
                grid0.levels,
                grid0.members,
            )
        grd_new = meb.grid_data(grid_new)

        for i in range(len(levels)):
            for j in range(len(times)):
                for k in range(len(dtimes)):
                    for m in range(len(members)):
                        dat = grd.values[m, i, j, k, :, :]
                        x = (
                            (np.arange(grid_new.nlon) * grid_new.dlon + grid_new.slon - grid0.slon)
                            / grid0.dlon
                        )
                        ig = np.around(x[:]).astype(dtype="int16")
                        y = (
                            (np.arange(grid_new.nlat) * grid_new.dlat + grid_new.slat - grid0.slat)
                            / grid0.dlat
                        )
                        jg = np.around(y[:]).astype(dtype="int16")
                        if iscycle:
                            ig = np.mod(ig, icycle)
                        else:
                            ig = np.minimum(np.maximum(ig, 0), grid0.nlon - 1)
                        jg = np.minimum(np.maximum(jg, 0), grid0.nlat - 1)
                        ii, jj = np.meshgrid(ig, jg)
                        grd_new.values[m, i, j, k, :, :] = dat[jj, ii]

        if is_out:
            grid_new1 = meb.grid(
                grid.glon,
                grid.glat,
                grid0.gtime,
                grid0.dtimes,
                grid0.levels,
                grid0.members,
            )
            grd_new = meb.expand_to_contain_another_grid(
                grd_new, grid_new1, outer_value=fill
            )
        grd_new.attrs = copy.deepcopy(grd.attrs)
        return grd_new
