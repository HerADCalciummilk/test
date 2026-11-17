# -*- coding: utf-8 -*-
"""站点→格点局部普通克里金（Ordinary Kriging）。

接口与 ``InterpSgIdw`` 对齐：``process(sta, grid, background=None)``。

算法要点
--------
1. 有背景场时先算站点偏差 ``obs - bg_at_sta``，插完再叠回背景；无背景则直接插站点值。
2. 对每个目标格点，用 KDTree 取 ``nearNum`` 个近邻站，建立局部普通克里金方程组：

       γ(si, sj) λj + μ = γ(si, x0)
       Σ λj = 1

   估计值 = Σ λj · zj。矩阵奇异时该点退化为反距离加权。
3. 变异函数 γ(h) 描述「距离越远、相关性越弱」，可选球状 / 指数 / 高斯模型。
4. ``sill``（基台）、``range_``（变程）未给出时按当前站点样本自动估计；
   ``nugget``（块金）表示零距离处的不连续方差。
"""
from __future__ import annotations

import copy
import os
import sys
from typing import Literal, Optional

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist

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

VariogramModel = Literal["spherical", "exponential", "gaussian"]


class InterpSgKriging(PostProcessingPlugin):
    """站点→格点局部普通克里金。

    - ``background is None``：直接插站点值。
    - 给出 ``background``：先插偏差，再叠回背景场。
    - 每个格点取 ``nearNum`` 个近邻站建立局部 OK 方程组（非全局一次求解）。

    Parameters
    ----------
    model :
        变异函数模型。``spherical`` 球状；``exponential`` 指数；``gaussian`` 高斯。
        指数/高斯式中 ``range_`` 按有效变程使用（约 95% 基台处）。
    sill :
        基台值。``None`` 时用当前切片站点值的方差。
    range_ :
        变程，单位与球面笛卡尔距离一致（米量级）。``None`` 时用近邻距离中位数粗估。
    nugget :
        块金值，``γ(0)=nugget``，须 ``>=0`` 且小于基台。
    nearNum :
        每个格点参与求解的近邻站点数。
    outer_value :
        背景场对齐越界填充值，传给 ``InterpGgLinear``。
    """

    def __init__(
        self,
        model: VariogramModel = "spherical",
        sill: Optional[float] = None,
        range_: Optional[float] = None,
        nugget: float = 0.0,
        nearNum: int = 20,
        outer_value: Optional[float] = None,
    ):
        if model not in ("spherical", "exponential", "gaussian"):
            raise ValueError("model 仅支持 spherical / exponential / gaussian")
        if int(nearNum) < 1:
            raise ValueError("nearNum 必须 >= 1")
        if float(nugget) < 0.0:
            raise ValueError("nugget 不能为负")
        self.model = model
        self.sill = sill
        self.range_ = range_
        self.nugget = float(nugget)
        self.nearNum = int(nearNum)
        self.outer_value = outer_value

    @staticmethod
    def _variogram(
        h: np.ndarray,
        model: VariogramModel,
        sill: float,
        range_: float,
        nugget: float = 0.0,
    ) -> np.ndarray:
        """计算变异函数 γ(h)。

        - h=0 → nugget
        - h 增大 → 趋近 sill（距离越远，半方差越大、相关性越弱）
        """
        h = np.asarray(h, dtype=np.float64)
        sill = float(sill)
        nugget = float(nugget)
        out = np.empty(h.shape, dtype=np.float64)

        zero = h <= 0.0
        out[zero] = nugget
        if not np.any(~zero):
            return out

        hh = h[~zero]
        if range_ <= 0.0:
            out[~zero] = sill
            return out

        if model == "spherical":
            # 变程内三次多项式，变程外取基台
            inside = hh <= range_
            hr = hh[inside] / range_
            g = np.full(hh.shape, sill, dtype=np.float64)
            g[inside] = nugget + (sill - nugget) * (1.5 * hr - 0.5 * hr ** 3)
        elif model == "exponential":
            g = nugget + (sill - nugget) * (1.0 - np.exp(-3.0 * hh / range_))
        else:  # gaussian
            g = nugget + (sill - nugget) * (1.0 - np.exp(-3.0 * (hh / range_) ** 2))

        out[~zero] = g
        return out

    @staticmethod
    def _estimate_range(xyz: np.ndarray, k: int = 8) -> float:
        """未指定变程时：取各站第 k 近邻距离中位数的 4 倍作为粗估。"""
        n = int(xyz.shape[0])
        if n <= 1:
            return 1.0
        kk = min(max(k, 2), n)
        d, _ = cKDTree(xyz).query(xyz, k=kk)
        nn = np.asarray(d[:, -1] if kk > 1 else d, dtype=np.float64)
        positive = nn[nn > 0]
        if positive.size == 0:
            return 1.0
        return float(np.median(positive) * 4.0)

    def _krige_point(
        self,
        xyz_neigh: np.ndarray,
        values: np.ndarray,
        xyz_target: np.ndarray,
        sill: float,
        range_: float,
    ) -> float:
        """单个目标点的局部普通克里金。

        组装 (n+1)×(n+1) 方程组（前 n 行为变异函数约束，末行为 Σλ=1），
        解出权重 λ 后做加权平均。奇异时退化为距离平方反比 IDW。
        """
        xyz_neigh = np.asarray(xyz_neigh, dtype=np.float64)
        values = np.asarray(values, dtype=np.float64).reshape(-1)
        xyz_target = np.asarray(xyz_target, dtype=np.float64).reshape(1, -1)
        n = values.size
        if n == 0:
            return 0.0
        if n == 1:
            return float(values[0])

        # 站-站、站-目标 半方差
        gamma_ss = self._variogram(
            cdist(xyz_neigh, xyz_neigh), self.model, sill, range_, self.nugget
        )
        d0 = cdist(xyz_neigh, xyz_target).ravel()
        gamma_s0 = self._variogram(d0, self.model, sill, range_, self.nugget)
        # 对角微扰，减轻共线/重合站点导致的奇异
        np.fill_diagonal(gamma_ss, gamma_ss.diagonal() + 1e-10)

        a = np.ones((n + 1, n + 1), dtype=np.float64)
        a[:n, :n] = gamma_ss
        a[-1, -1] = 0.0
        rhs = np.empty(n + 1, dtype=np.float64)
        rhs[:n] = gamma_s0
        rhs[-1] = 1.0

        try:
            lam = np.linalg.solve(a, rhs)
        except np.linalg.LinAlgError:
            w = 1.0 / (d0 + 1e-6) ** 2
            return float(np.dot(w, values) / np.sum(w))
        return float(np.dot(lam[:n], values))

    def _krige_grid(
        self,
        xyz_sta: np.ndarray,
        values: np.ndarray,
        xyz_grid: np.ndarray,
    ) -> np.ndarray:
        """整张网格：逐格点取近邻站并调用 ``_krige_point``。"""
        xyz_sta = np.asarray(xyz_sta, dtype=np.float64)
        values = np.asarray(values, dtype=np.float64).reshape(-1)
        xyz_grid = np.asarray(xyz_grid, dtype=np.float64)
        n_sta = values.size
        n_grid = xyz_grid.shape[0]
        if n_sta == 0:
            return np.zeros(n_grid, dtype=np.float32)

        # 基台 / 变程：显式参数优先，否则按本切片站点自动估计
        sill = float(np.var(values)) if self.sill is None else float(self.sill)
        if not np.isfinite(sill) or sill <= 0.0:
            sill = 1e-6
        if self.nugget >= sill:
            sill = self.nugget + 1e-6

        range_ = self._estimate_range(xyz_sta) if self.range_ is None else float(self.range_)
        if range_ <= 0.0:
            range_ = 1.0

        k = min(self.nearNum, n_sta)
        _, inds = cKDTree(xyz_sta).query(xyz_grid, k=k)
        if k == 1:
            inds = np.asarray(inds, dtype=np.intp).reshape(-1, 1)
        else:
            inds = np.asarray(inds, dtype=np.intp)

        out = np.empty(n_grid, dtype=np.float64)
        for i in range(n_grid):
            idx = inds[i]
            out[i] = self._krige_point(xyz_sta[idx], values[idx], xyz_grid[i], sill, range_)
        return out.astype(np.float32)

    def process(self, sta0, grid, background=None):
        """站点→格点克里金插值。

        Args:
            sta0: 站点数据。
            grid: 目标网格信息（含 ``glon`` / ``glat`` 等）。
            background: 可选背景场；给出时走偏差订正（插偏差后叠回背景）。

        Returns:
            与站点 member/level/time/dtime 切片拼接后的格点场；``attrs`` 继承自 ``sta0``。
        """
        import meteva_base as meb

        sta1 = meb.sele_by_para(sta0, drop_IV=True)
        grd_list = []
        for sta in meb.split(sta1, ["member", "level", "time", "dtime"]):
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

            # 可选：背景场偏差订正
            if background is not None:
                bg = InterpGgLinear(outer_value=self.outer_value).process(background, grid2)
                if bg is None:
                    raise ValueError(
                        "背景场对齐失败：目标网格超出背景范围时请设置 outer_value"
                    )
                sta_use = sta.copy()
                sta_use.iloc[:, -1] = (
                    sta.iloc[:, -1] - meb.interp_gs_linear(bg, sta).iloc[:, -1]
                )
            else:
                bg = None
                sta_use = sta

            # 经纬度 → 球面笛卡尔坐标，保证距离为弧长意义下的欧氏距离
            lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
            lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
            grid_lon, grid_lat = np.meshgrid(lon, lat)
            xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(
                sta_use["lon"].values,
                sta_use["lat"].values,
                R=meb.basicdata.const.ER,
            )
            xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(
                grid_lon.flatten(),
                grid_lat.flatten(),
                R=meb.basicdata.const.ER,
            )

            dat = self._krige_grid(xyz_sta, sta_use.iloc[:, -1].values, xyz_grid)

            if background is not None:
                grd = bg.copy()
                grd.values = grd.values + meb.basicdata.grid_data(grid2, dat).values
                grd.name = "data0"
            else:
                grd = meb.basicdata.grid_data(grid2, dat)
                grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        grd_all.attrs = copy.deepcopy(sta0.attrs)
        return grd_all
