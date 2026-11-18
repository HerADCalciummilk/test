# -*- coding: utf-8 -*-
"""格点→格点双线性插值。

接口：``process(grd, grid)``。
算法参考独立包 ``interp_gg_linear``（含全球循环场纬度越界检查）；
依赖 ``meteva_base``，不直接调用库内 ``interp_gg_linear``（库在循环场时不查纬度）。

算法要点
--------
1. 将目标格点映射到源网格索引分数，四角双线性加权。
2. 源场经度跨满 360°（``iscycle``）时经度下标取模；纬度越界仍须 ``outer_value``。
3. 非循环场经纬任一越界：先插重叠区，再 ``expand_to_contain_another_grid`` 填外区。
4. member / level / time / dtime 沿用源场；水平网格取自目标 ``grid``。
"""
from __future__ import annotations

import copy
from typing import Optional

import meteva_base as meb
import numpy as np

from utils.base_plugin import PostProcessingPlugin


class InterpGgLinear(PostProcessingPlugin):
    """格点→格点双线性插值（水平）。

    Parameters
    ----------
    outer_value :
        目标超出源网格时的填充值；越界时必须提供，否则返回 ``None``。
    """

    def __init__(self, outer_value: Optional[float] = None):
        self.outer_value = outer_value

    def process(self, grd, grid):
        """格点→格点双线性插值。

        Args:
            grd: 源格点场。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。

        Returns:
            插值到目标网格的格点场；``grd is None`` 或越界未给 ``outer_value`` 时为 ``None``。
        """
        fill = self.outer_value
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
            # 经度可周期；纬度越界仍须 outer_value（独立包行为，异于库方法）
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
                        ig = x[:].astype(dtype="int16")
                        dx = x - ig
                        y = (
                            (np.arange(grid_new.nlat) * grid_new.dlat + grid_new.slat - grid0.slat)
                            / grid0.dlat
                        )
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
                        dat2 = (
                            c00 * dat[jj, ii]
                            + c10 * dat[jj1, ii]
                            + c01 * dat[jj, ii1]
                            + c11 * dat[jj1, ii1]
                        )
                        grd_new.values[m, i, j, k, :, :] = dat2

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
