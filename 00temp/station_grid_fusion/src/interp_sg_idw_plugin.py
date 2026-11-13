# -*- coding: utf-8 -*-
"""站点→格点反距离权重插值（IDW），可选背景偏差与高斯衰减。

接口：``process(sta, grid, background=None)``。

算法要点
--------
1. 有背景场时先算站点偏差 ``obs - bg_at_sta``，插完再叠回背景；无背景则直接插站点值。
2. 经纬度转到球面笛卡尔坐标后，用 KDTree 为每个格点找 ``nearNum`` 个近邻站。
3. 权重：

   - ``gaussian=False``（纯 IDW）：``w = 1 / d^decrease``。
     ``effectR`` 为硬截断半径——最近站距离超过该值时，无背景填 0，有背景则偏差置 0（保留背景）。
   - ``gaussian=True``（IDW×高斯，原 InterpSgIdwDelta）：
     ``w = (1 / d^decrease) * exp(-(d / effectR)^2)``，``effectR`` 作高斯半径；
     归一化分母仍用 IDW 权重和（与历史实现一致）。
4. 按 member / level / time / dtime 切片分别插值后拼接。
"""
from __future__ import annotations

from typing import Optional

import meteva_base as meb
import numpy as np
from scipy.spatial import cKDTree

from utils.base_plugin import PostProcessingPlugin


class InterpSgIdw(PostProcessingPlugin):
    """站点到格点 IDW 插值。

    - ``background is None``：直接插值站点值。
    - 给出 ``background``：先算偏差，再插值并叠回背景场。
    - ``gaussian=False``：纯 IDW，``effectR`` 为硬截断半径。
    - ``gaussian=True``：IDW × 高斯，``effectR`` 为高斯半径。

    Parameters
    ----------
    effectR :
        纯 IDW 时为影响半径上限（硬截断）；高斯模式下为高斯衰减尺度。
        距离单位与球面笛卡尔坐标一致（米量级）。
    nearNum :
        每个格点参与加权的近邻站点数。
    decrease :
        距离衰减指数，对应 ``1 / d^decrease``。
    gaussian :
        是否乘高斯核。为真时对应原 ``InterpSgIdwDelta`` 的权重形式。
    """

    def __init__(
        self,
        effectR: Optional[int] = 1000,
        nearNum: Optional[int] = 8,
        decrease: Optional[int] = 2,
        gaussian: bool = False,
        outer_value: Optional[float] = None,
    ):
        self.effectR = effectR
        self.nearNum = nearNum
        self.decrease = decrease
        self.gaussian = bool(gaussian)
        self.outer_value = outer_value

    def process(self, sta0, grid, background=None):
        """站点→格点插值。

        Args:
            sta0: 站点数据。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。
            background: 可选背景场；给出时走偏差订正路径。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场。
        """
        sta1 = meb.sele_by_para(sta0, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []
        for sta in sta_list:
            data_name = meb.get_stadata_names(sta)
            index0 = sta.index[0]
            dtime = int(sta.loc[index0, "dtime"])
            level = int(sta.loc[index0, "level"])
            # 按本切片的 time/dtime/level 构造目标网格
            grid2 = meb.basicdata.grid(
                grid.glon,
                grid.glat,
                [sta.loc[index0, "time"]],
                [dtime],
                [level],
                data_name,
            )

            # 可选：背景场偏差订正（插值对象变为 obs - bg）
            if background is not None:
                bg = meb.interp_gg_linear(background, grid=grid2, outer_value=self.outer_value)
                sta_use = sta.copy()
                bg_at_sta = meb.interp_gs_linear(bg, sta)
                sta_use.iloc[:, -1] = sta.iloc[:, -1] - bg_at_sta.iloc[:, -1]
            else:
                bg = None
                sta_use = sta

            # 经纬度 → 球面笛卡尔坐标，保证距离为弧长意义下的欧氏距离
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
            tree = cKDTree(xyz_sta)
            near_num = self.nearNum if self.nearNum <= len(sta_use.index) else len(sta_use.index)
            # d: 格点到近邻站距离；inds: 近邻站索引
            d, inds = tree.query(xyz_grid, k=near_num)

            if near_num > 1:
                d = d + 1e-6  # 避免零距离导致权重无穷大
                w_idw = 1.0 / d ** self.decrease
                input_dat = sta_use.values[:, -1]
                if self.gaussian:
                    # IDW × 高斯；分母仍用 Σ w_idw（历史约定）
                    w_gauss = np.exp(-(d / self.effectR) ** 2)
                    dat = np.sum(w_idw * w_gauss * input_dat[inds], axis=1) / np.sum(w_idw, axis=1)
                else:
                    # 纯 IDW；超硬截断半径则填 0（有背景时等价于偏差为 0）
                    dat = np.sum(w_idw * input_dat[inds], axis=1) / np.sum(w_idw, axis=1)
                    fill = 0.0 if background is not None else meb.basicdata.grid_data(grid2).values.flatten()
                    dat = np.where(d[:, 0] > self.effectR, fill, dat)
            else:
                # 仅 1 个近邻：最近邻赋值，可选高斯衰减 / 硬截断
                input_dat = sta_use.iloc[:, -1].values
                if self.gaussian:
                    w_gauss = np.exp(-(d / self.effectR) ** 2)
                    dat = w_gauss * input_dat[inds]
                    dat[d > self.effectR] = 0
                else:
                    dat = input_dat[inds]
                    fill = 0.0 if background is not None else meb.basicdata.grid_data(grid2).values.flatten()
                    dat = np.where(d[:] > self.effectR, fill, dat)

            dat = dat.astype(np.float32)
            if background is not None:
                # 偏差场叠回背景
                grd_delta = meb.basicdata.grid_data(grid2, dat)
                grd = bg.copy()
                grd.values = grd.values + grd_delta.values
                grd.name = "data0"
            else:
                grd = meb.basicdata.grid_data(grid2, dat)
                grd.name = data_name[0]
            grd_list.append(grd)

        return meb.concat(grd_list)
