# -*- coding: utf-8 -*-
"""站点→格点 Cressman 插值（可选背景初值场）。

接口与 ``InterpSgIdw`` 对齐：``process(sta, grid, background=None)``。
实现参考 ``utils.interpolating.interp_sg_cressman``；
``k=1`` 维数与 ``w_sum==0`` 防护参考独立包 ``interp_sg_cressman``。

算法要点
--------
1. 初值场：无背景为 0 场；有背景时先将背景双线性对齐到目标网格。
   （与 IDW/Kriging 的「偏差订正再叠回」不同：此处背景作初估场，半径内由
   Cressman 加权均值直接改写。）
2. 对每个格点查 ``nearNum`` 近邻站；按 ``r_list`` 逐级订正，权重
   ``w = (R^2 - d^2) / (R^2 + d^2)``（``w < 0`` 置 0）。
3. 按 member / level / time / dtime 切片分别插值后拼接。
"""
from __future__ import annotations

from typing import Optional, Sequence

import meteva_base as meb
import numpy as np
from scipy.spatial import cKDTree

from utils.base_plugin import PostProcessingPlugin

_DEFAULT_R_LIST = (60000.0, 40000.0, 20000.0)


class InterpSgCressman(PostProcessingPlugin):
    """站点→格点 Cressman 逐步订正。

    - ``background is None``：初值为 0，再按半径列表用站点加权改写。
    - 给出 ``background``：初值为对齐后的背景场，再逐步改写影响半径内的格点。

    Parameters
    ----------
    r_list :
        Cressman 影响半径列表（米制笛卡尔距离），按顺序逐级订正。
    nearNum :
        每个格点参与加权的近邻站点数上限。
    """

    def __init__(
        self,
        model_id_attr: Optional[str] = None,
        r_list: Optional[Sequence[float]] = None,
        nearNum: int = 100,
    ):
        if int(nearNum) < 1:
            raise ValueError("nearNum 必须 >= 1")
        radii = list(_DEFAULT_R_LIST if r_list is None else r_list)
        if not radii:
            raise ValueError("r_list 不能为空")
        for r in radii:
            if float(r) <= 0:
                raise ValueError("r_list 中半径必须大于 0")
        self.model_id_attr = model_id_attr
        self.r_list = [float(r) for r in radii]
        self.nearNum = int(nearNum)

    def process(self, sta0, grid, background=None):
        """站点→格点 Cressman 插值。

        Args:
            sta0: 站点数据。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。
            background: 可选背景初值场；给出时先对齐到目标网格再订正。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场。
        """
        sta1 = meb.sele_by_para(sta0, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []

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

            xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(
                sta["lon"].values,
                sta["lat"].values,
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
            nsta = len(sta.index)
            k_near = self.nearNum if self.nearNum <= nsta else nsta
            d, inds = tree.query(xyz_grid, k=k_near)
            d = np.asarray(d, dtype=float) + 1e-6
            inds = np.asarray(inds)

            # 初值：0 场，或背景场对齐到目标网格
            bg = meb.basicdata.grid_data(grid2)
            if background is not None:
                bg = meb.interp_gg_linear(background, grid=grid2)

            bg_dat = np.asarray(bg.values, dtype=float).flatten()
            input_dat = sta.values[:, -1]

            # query(k=1) 时 d/inds 为一维，统一成二维便于后续切片
            if d.ndim == 1:
                d = d[:, np.newaxis]
                inds = inds[:, np.newaxis]

            d2 = d ** 2
            for R in self.r_list:
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

            grd = meb.basicdata.grid_data(grid2, bg_dat.astype(np.float32))
            grd.name = data_name[0]
            grd_list.append(grd)

        return meb.concat(grd_list)
