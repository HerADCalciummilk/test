# -*- coding: utf-8 -*-
"""格点→格点双三次插值。

接口：``process(grd, grid)``。
算法参考 ``utils.interpolating.interp_gg_cubic``；
越界判定与 ``InterpGgLinear`` 对齐（全球循环场仍检查纬度越界）。
依赖 ``meteva_base``，不直接调用库内 ``interp_gg_cubic``。

算法要点
--------
1. 将目标格点映射到源网格索引分数，对 ``p,q ∈ {-1,0,1,2}`` 用三次核 ``cubic_f`` 加权累加。
2. 邻点下标按源网格边界钳制（与 ``interpolating`` 一致）。
3. 源场经度跨满 360°（``iscycle``）时：纬度越界仍须 ``outer_value``。
4. 非循环场经纬任一越界：先插重叠区，再 ``expand_to_contain_another_grid`` 填外区。
5. member / level / time / dtime 沿用源场；水平网格取自目标 ``grid``。
"""
from __future__ import annotations

import copy
from typing import Optional

import meteva_base as meb
import numpy as np

from utils.base_plugin import PostProcessingPlugin


class InterpGgCubic(PostProcessingPlugin):
    """格点→格点双三次插值（水平）。

    Parameters
    ----------
    outer_value :
        目标超出源网格时的填充值；越界时必须提供，否则返回 ``None``。
    """

    def __init__(self, outer_value: Optional[float] = None):
        self.outer_value = outer_value

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

    def process(self, grd, grid):
        """格点→格点双三次插值。

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
                        ig = x[:].astype(dtype="int16")
                        dx = x - ig
                        y = (
                            (np.arange(grid_new.nlat) * grid_new.dlat + grid_new.slat - grid0.slat)
                            / grid0.dlat
                        )
                        jg = y[:].astype(dtype="int16")
                        dy = y - jg
                        ii, jj = np.meshgrid(ig, jg)
                        for p in range(-1, 3, 1):
                            iip = np.minimum(np.maximum(ii + p, 0), grid0.nlon - 1)
                            fdx = self._cubic_f(p, dx)
                            for q in range(-1, 3, 1):
                                jjq = np.minimum(np.maximum(jj + q, 0), grid0.nlat - 1)
                                fdy = self._cubic_f(q, dy)
                                fdxx, fdyy = np.meshgrid(fdx, fdy)
                                fdxy = fdxx * fdyy
                                grd_new.values[m, i, j, k, :, :] += fdxy * dat[jjq, iip]

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
