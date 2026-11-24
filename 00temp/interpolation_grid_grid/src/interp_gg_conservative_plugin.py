# -*- coding: utf-8 -*-
"""格点→格点一阶面积加权（守恒）插值。

接口：``process(grd, grid)``。算法对齐 Iris ``AreaWeighted``：按正交规则经纬
格元重叠面积加权；球面用 ``Δlon × Δsin(lat)`` 等价的分离权重外积。

算法要点
--------
1. 由等距中心点生成 contiguous 格边，构建稀疏面积权重。
2. 源场经度跨满 360°（``iscycle``）时经度按周期处理。
3. 非循环场经纬越界：先对重叠区做面积加权，再 ``expand_to_contain_another_grid``。
4. member / level / time / dtime 沿用源场；水平网格取自目标 ``grid``。
"""
from __future__ import annotations

import copy
from typing import Optional

import meteva_base as meb
import numpy as np

from utils.area_weighted import (
    apply_area_weighted,
    build_area_weighted_weights,
    contiguous_bounds_1d,
)
from utils.base_plugin import PostProcessingPlugin


class InterpGgConservative(PostProcessingPlugin):
    """格点→格点一阶面积加权守恒插值（水平）。

    Parameters
    ----------
    outer_value :
        目标超出源网格（或有效覆盖不足）时的填充值；越界时必须提供，否则返回 ``None``。
    mdtol :
        缺测/覆盖容差，范围 ``[0, 1]``，语义同 Iris ``AreaWeighted``。默认 ``1``。
    spherical :
        是否按球面面积因子（``sin(lat)``）计算。默认 ``True``。
    """

    def __init__(
        self,
        outer_value: Optional[float] = None,
        mdtol: float = 1.0,
        spherical: bool = True,
    ):
        if not (0.0 <= float(mdtol) <= 1.0):
            raise ValueError("mdtol 须在 [0, 1]")
        self.outer_value = outer_value
        self.mdtol = float(mdtol)
        self.spherical = bool(spherical)

    @staticmethod
    def _bounds_from_grid(grid) -> tuple[np.ndarray, np.ndarray]:
        """由 ``meb.grid`` 生成 lon/lat contiguous bounds。"""
        lons = (
            np.arange(int(grid.nlon), dtype=np.float64) * float(grid.dlon)
            + float(grid.slon)
        )
        lats = (
            np.arange(int(grid.nlat), dtype=np.float64) * float(grid.dlat)
            + float(grid.slat)
        )
        return (
            contiguous_bounds_1d(lons, spacing=float(grid.dlon)),
            contiguous_bounds_1d(lats, spacing=float(grid.dlat)),
        )

    def process(self, grd, grid):
        """格点→格点面积加权插值。

        Args:
            grd: 源格点场（正交规则经纬六维场）。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。

        Returns:
            插值到目标网格的格点场；``grd is None`` 或越界未给 ``outer_value`` 时为 ``None``。
        """
        fill = self.outer_value
        if grd is None:
            return None

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

        src_lon_b, src_lat_b = self._bounds_from_grid(grid0)
        tgt_lon_b, tgt_lat_b = self._bounds_from_grid(grid_new)
        weights = build_area_weighted_weights(
            src_lon_b,
            src_lat_b,
            tgt_lon_b,
            tgt_lat_b,
            spherical=self.spherical,
            circular_lon=bool(iscycle),
        )

        # 一次处理全部切片：values 形状 (member, level, time, dtime, lat, lon)
        dat = np.asarray(grd.values, dtype=np.float64)
        remapped = apply_area_weighted(
            dat,
            weights,
            grid_new.nlat,
            grid_new.nlon,
            mdtol=self.mdtol,
            fill_value=fill if fill is not None else np.nan,
        )
        # 覆盖不足时若未给 fill，上面写了 NaN；此时与 linear 一致地要求 outer_value
        if fill is None and not np.all(np.isfinite(remapped)):
            print("当目标网格超出数据网格时，outer_value参数必须赋值")
            return None

        grd_new = meb.grid_data(grid_new, remapped)
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
