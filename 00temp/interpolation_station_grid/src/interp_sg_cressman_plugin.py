# -*- coding: utf-8 -*-
"""站点→格点 Cressman 逐步订正（可选背景初估场）。

接口与 ``InterpSgIdw`` 对齐：``process(sta, grid, background=None)``。
权重形式参考 ``utils.interpolating.interp_sg_cressman``；
本实现采用经典逐步订正：每一扫相对**当前分析场**计算增量。

算法要点
--------
1. 初估场：无背景为 0；有背景时双线性对齐到目标网格。
2. 对 ``r_list`` 中每个半径 R，执行一次扫描：

       innov_i = obs_i − analysis_at_sta_i
       analysis(x) ← analysis(x) + Σ w_i·innov_i / Σ w_i

   其中 ``w = (R^2 − d^2) / (R^2 + d^2)``（``d ≥ R`` 时 ``w = 0``）。
3. 下一扫在更新后的分析场上重新取站点值，再算创新量。
4. 按 member / level / time / dtime 切片分别订正后拼接。
"""
from __future__ import annotations

import copy
import os
import sys
from typing import Optional, Sequence

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

_DEFAULT_R_LIST = (60000.0, 40000.0, 20000.0)


class InterpSgCressman(PostProcessingPlugin):
    """站点→格点 Cressman 逐步订正。

    - ``background is None``：初估为 0 场，再按 ``r_list`` 逐步增量订正。
    - 给出 ``background``：初估为对齐后的背景场，再逐步增量订正。

    Parameters
    ----------
    r_list :
        影响半径列表（米制笛卡尔距离），按顺序逐扫，通常由大到小。
    nearNum :
        每个格点参与加权的近邻站点数上限。
    outer_value :
        背景场对齐越界填充值，传给 ``InterpGgLinear``。
    """

    def __init__(
        self,
        r_list: Optional[Sequence[float]] = None,
        nearNum: int = 100,
        outer_value: Optional[float] = None,
    ):
        if int(nearNum) < 1:
            raise ValueError("nearNum 必须 >= 1")
        radii = list(_DEFAULT_R_LIST if r_list is None else r_list)
        if not radii:
            raise ValueError("r_list 不能为空")
        for r in radii:
            if float(r) <= 0:
                raise ValueError("r_list 中半径必须大于 0")
        self.r_list = [float(r) for r in radii]
        self.nearNum = int(nearNum)
        self.outer_value = outer_value

    def process(self, sta0, grid, background=None):
        """站点→格点 Cressman 逐步订正。

        Args:
            sta0: 站点数据。
            grid: 目标网格信息（``glon`` / ``glat`` 等）。
            background: 可选背景初估场；给出时先对齐到目标网格再订正。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场；``attrs`` 继承自 ``sta0``。
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
            if d.ndim == 1:
                d = d[:, np.newaxis]
                inds = inds[:, np.newaxis]
            d2 = d ** 2

            # 初估场
            ana_grd = meb.basicdata.grid_data(grid2)
            if background is not None:
                ana_grd = InterpGgLinear(outer_value=self.outer_value).process(
                    background, grid2
                )
                if ana_grd is None:
                    raise ValueError(
                        "背景场对齐失败：目标网格超出背景范围时请设置 outer_value"
                    )
            ana_dat = np.asarray(ana_grd.values, dtype=float).flatten()
            obs = np.asarray(sta.values[:, -1], dtype=float)

            for R in self.r_list:
                # 当前分析场 → 站点，得本扫创新量
                ana_grd = meb.basicdata.grid_data(grid2, ana_dat)
                ana_at_sta = meb.interp_gs_linear(ana_grd, sta).iloc[:, -1].values
                innov = obs - ana_at_sta

                index_in = np.where(d[:, 0] < R)[0]
                if len(index_in) == 0:
                    continue
                inds_in = inds[index_in, :]
                r2 = R ** 2
                w = (r2 - d2[index_in, :]) / (r2 + d2[index_in, :])
                w[w < 0] = 0
                w_sum = np.sum(w, axis=1)
                valid = w_sum > 0
                if not np.any(valid):
                    continue
                idx_valid = index_in[valid]
                corr = np.sum(w[valid] * innov[inds_in[valid]], axis=1) / w_sum[valid]
                ana_dat[idx_valid] = ana_dat[idx_valid] + corr

            grd = meb.basicdata.grid_data(grid2, ana_dat.astype(np.float32))
            grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        grd_all.attrs = copy.deepcopy(sta0.attrs)
        return grd_all
