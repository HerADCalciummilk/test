# -*- coding: utf-8 -*-
"""站点→格点最近邻×高斯插值（可选背景偏差订正）。

接口与 ``InterpSgIdw`` 对齐：``process(sta, grid, background=None)``。
实现参考 ``utils.interpolating.interp_sg_delta_gaussian``。

算法要点
--------
1. 有背景场时先算站点偏差 ``obs - bg_at_sta``，插完再叠回背景；无背景则直接插站点值。
2. 每个格点只取最近 1 个站，权重 ``w = exp(-(d / halfR)^2)``；``d > halfR`` 时置 0。
3. 按 member / level / time / dtime 切片分别插值后拼接。
"""
from __future__ import annotations

import copy
import os
import sys
from typing import Optional

import meteva_base as meb
import numpy as np
from scipy.spatial import cKDTree

from utils.base_plugin import PostProcessingPlugin


def _ensure_interpolation_grid_grid_on_path() -> None:
    """将同级子模块 ``interpolation_grid_grid`` 的根与 ``src`` 追加到 sys.path。"""
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    gg_root = os.path.join(temp_root, "interpolation_grid_grid")
    gg_src = os.path.join(gg_root, "src")
    for p in (gg_root, gg_src):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_ensure_interpolation_grid_grid_on_path()

from interp_gg_linear_plugin import InterpGgLinear  # noqa: E402


class InterpSgGaussian(PostProcessingPlugin):
    """最近邻 × 高斯半径扩散。

    - ``background is None``：直接插值站点值。
    - 给出 ``background``：先算偏差，再高斯扩散并叠回背景场。

    Parameters
    ----------
    halfR :
        高斯半径；超过该距离的格点权重置 0。
        距离单位与球面笛卡尔坐标一致（米量级）。
    outer_value :
        背景场对齐越界填充值，传给 ``InterpGgLinear``。
    """

    def __init__(
        self,
        halfR: Optional[int] = 20,
        outer_value: Optional[float] = None,
    ):
        if halfR is not None and int(halfR) <= 0:
            raise ValueError("halfR 必须大于 0")
        self.halfR = 20 if halfR is None else int(halfR)
        self.outer_value = outer_value

    def process(self, sta0, grid, background=None):
        """站点→格点最近邻高斯插值。

        Args:
            sta0: 站点数据。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。
            background: 可选背景场；给出时走偏差订正路径。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场；``attrs`` 继承自 ``sta0``。
        """
        sta1 = meb.sele_by_para(sta0, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []
        half_r = float(self.halfR)

        for sta in sta_list:
            data_name = meb.get_stadata_names(sta)
            index0 = sta.index[0]
            grid2 = meb.basicdata.grid(
                grid.glon,
                grid.glat,
                [sta.loc[index0, "time"]],
                [int(sta.loc[index0, "dtime"])],
                [int(sta.loc[index0, "level"])],
                data_name,
            )

            # 可选：背景场偏差订正（插值对象变为 obs - bg）
            if background is not None:
                bg = InterpGgLinear(outer_value=self.outer_value).process(background, grid2)
                if bg is None:
                    raise ValueError(
                        "背景场对齐失败：目标网格超出背景范围时请设置 outer_value"
                    )
                sta_use = sta.copy()
                bg_at_sta = meb.interp_gs_linear(bg, sta)
                sta_use.iloc[:, -1] = sta.iloc[:, -1] - bg_at_sta.iloc[:, -1]
            else:
                bg = None
                sta_use = sta

            # 经纬度 → 球面笛卡尔坐标
            xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(
                sta_use["lon"].values,
                sta_use["lat"].values,
                R=meb.basicdata.const.ER,
            )
            lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
            lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
            grid_lon, grid_lat = np.meshgrid(lon, lat)
            xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(
                grid_lon.flatten(),
                grid_lat.flatten(),
                R=meb.basicdata.const.ER,
            )

            # 最近邻 × 高斯；超半径置 0
            tree = cKDTree(xyz_sta)
            d, inds = tree.query(xyz_grid, k=1)
            input_dat = sta_use.iloc[:, -1].values
            w_gauss = np.exp(-(d / half_r) ** 2)
            dat = w_gauss * input_dat[inds]
            dat[d > half_r] = 0
            dat = dat.astype(np.float32)

            if background is not None:
                grd_delta = meb.basicdata.grid_data(grid2, dat)
                grd = bg.copy()
                grd.values = grd.values + grd_delta.values
                grd.name = "data0"
            else:
                grd = meb.basicdata.grid_data(grid2, dat)
                grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        grd_all.attrs = copy.deepcopy(sta0.attrs)
        return grd_all
