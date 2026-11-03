# -*- coding: utf-8 -*-
"""
站点 → 格点 Cressman 插值插件。

在目标网格上，按影响半径列表 ``r_list`` 逐步用邻近站点做 Cressman 加权订正；
若提供背景场，先经格点双线性插值对齐到目标网格。

函数入口：``interp_sg_cressman``
插件入口：``InterpSGCressmanPlugin``（可调用，``plugin(sta, grid)``）

依赖：``utils.interp_gg_pulgin.interp_gg_linear``（背景场对齐）。
"""

from __future__ import annotations

import copy
from typing import Optional, Sequence

import meteva
import meteva_base
import numpy as np
from scipy.spatial import cKDTree

from utils.base_plugin import BasePlugin
from utils.interp_gg_pulgin import interp_gg_linear


def interp_sg_cressman(sta0, grid, r_list, background=None, nearNum=100, outer_value=None):
    """
    站点到格点的 Cressman 插值。

    输入
    ----
    sta0 : meteva / meteva_base 站点数据
        站点场（可含 member/level/time/dtime；缺测会丢弃）。
    grid : meteva_base.grid
        目标水平网格（glon/glat）；时间维等按各站点子集填充。
    r_list : sequence of float
        Cressman 影响半径列表（米制笛卡尔距离，与 ``lon_lat_to_cartesian`` 一致），
        按顺序逐级订正。
    background : meteva 格点场, optional
        背景场；提供时通过 ``interp_gg_linear`` 插到目标网格作为初值，
        否则初值为 0 场。
    nearNum : int
        KDTree 查询的邻近站点数上限（不超过实际站数）。
    outer_value : float, optional
        背景场双线性插值越界时的填充值，传给 ``interp_gg_linear``。

    输出
    ----
    grd_all : meteva 格点场
        各 member/level/time/dtime 子集插值后拼接的结果；attrs 继承自 ``sta0``。
    """
    sta1 = meteva_base.sele_by_para(sta0, drop_IV=True)
    sta_list = meteva_base.split(sta1, ["member", "level", "time", "dtime"])
    grd_list = []
    for sta in sta_list:
        data_name = meteva_base.get_stadata_names(sta)
        index0 = sta.index[0]
        grid2 = meteva_base.basicdata.grid(
            grid.glon, grid.glat,
            [sta.loc[index0, "time"]],
            [sta.loc[index0, "dtime"]],
            [sta.loc[index0, "level"]],
            data_name,
        )
        xyz_sta = meteva_base.tool.math_tools.lon_lat_to_cartesian(
            sta["lon"].values,
            sta["lat"].values,
            R=meteva_base.basicdata.const.ER,
        )
        lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
        lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
        grid_lon, grid_lat = np.meshgrid(lon, lat)
        xyz_grid = meteva_base.tool.math_tools.lon_lat_to_cartesian(
            grid_lon.flatten(),
            grid_lat.flatten(),
            R=meteva_base.basicdata.const.ER,
        )
        tree = cKDTree(xyz_sta)
        nsta = len(sta.index)
        k_near = nearNum if nearNum <= nsta else nsta
        d, inds = tree.query(xyz_grid, k=k_near)
        d = np.asarray(d, dtype=float) + 1e-6
        inds = np.asarray(inds)

        bg = meteva_base.basicdata.grid_data(grid2)
        if background is not None:
            bg_interp = interp_gg_linear(background, grid2, outer_value=outer_value)
            if bg_interp is not None:
                bg = bg_interp

        bg_dat = np.asarray(bg.values, dtype=float).flatten()
        input_dat = sta.values[:, -1]

        # query(k=1) 时 d/inds 为一维，统一成二维便于后续切片
        if d.ndim == 1:
            d = d[:, np.newaxis]
            inds = inds[:, np.newaxis]

        d2 = d ** 2
        for R in r_list:
            index_in = np.where(d[:, 0] < R)[0]
            if len(index_in) == 0:
                continue
            inds_in = inds[index_in, :]
            r2 = R ** 2
            d2_in = d2[index_in, :]
            w = (r2 - d2_in) / (r2 + d2_in)
            w[w < 0] = 0
            w_sum = np.sum(w, axis=1)
            valid = w_sum > 0
            if not np.any(valid):
                continue
            idx_valid = index_in[valid]
            dat = np.sum(w[valid] * input_dat[inds_in[valid]], axis=1) / w_sum[valid]
            bg_dat[idx_valid] = dat[:]

        grd = meteva_base.basicdata.grid_data(grid2, bg_dat)
        grd.name = data_name[0]
        grd_list.append(grd)

    grd_all = meteva_base.concat(grd_list)
    grd_all.attrs = copy.deepcopy(sta0.attrs)
    return grd_all


class InterpSGCressmanPlugin(BasePlugin):
    """
    可调用站点→格点 Cressman 插值插件。

    用法::

        plugin = InterpSGCressmanPlugin(r_list=[60000, 40000, 20000], nearNum=100)
        grd = plugin(sta, grid, background=bg_grd)
        # 等价
        grd = plugin.process(sta, grid, background=bg_grd)
    """

    def __init__(
        self,
        r_list: Sequence[float],
        nearNum: int = 100,
        outer_value: Optional[float] = None,
    ):
        self.r_list = list(r_list)
        self.nearNum = nearNum
        self.outer_value = outer_value

    def process(self, sta0, grid, background=None, r_list=None, nearNum=None, outer_value=None):
        """
        输入: sta0（站点）, grid（目标网格）, background（可选背景格点）
        输出: Cressman 插值后的格点场
        """
        return interp_sg_cressman(
            sta0,
            grid,
            r_list=self.r_list if r_list is None else r_list,
            background=background,
            nearNum=self.nearNum if nearNum is None else nearNum,
            outer_value=self.outer_value if outer_value is None else outer_value,
        )
