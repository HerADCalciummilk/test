# -*- coding: utf-8 -*-
"""站点→格点最近邻×高斯插值（可选背景与偏差订正）。

接口：``process(sta, grid=None, background=None)``。

- ``reprocess=False``（默认）：插站点**绝对值**；``d > halfR`` 时回退背景
  （无背景则填 0）。须 ``grid``，或由 ``background`` 取网格。
- ``reprocess=True``：须 ``background``；插 ``obs - bg`` 再叠回。``grid`` 可省略。

权重：每格点最近 1 站，``w = exp(-(d / halfR)^2)``；超 ``halfR`` 硬截断。
"""
from __future__ import annotations

import copy
import os
import sys
from typing import Any, Optional

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

    - ``reprocess=False``：绝对值；超 ``halfR`` 用背景填（无背景填 0）。
    - ``reprocess=True``：偏差订正；须 ``background``；``grid`` 可省略。

    Parameters
    ----------
    halfR :
        高斯半径；超过该距离硬截断。距离为米量级。
    outer_value :
        背景场对齐越界填充，传给 ``InterpGgLinear``。
    reprocess :
        ``False``：绝对值 + 远点回退背景；``True``：偏差订正。
    """

    def __init__(
        self,
        halfR: Optional[int] = 20,
        outer_value: Optional[float] = None,
        reprocess: Any = False,
    ):
        if halfR is not None and int(halfR) <= 0:
            raise ValueError("halfR 必须大于 0")
        self.halfR = 20 if halfR is None else int(halfR)
        self.outer_value = outer_value
        self.reprocess = self._as_bool(reprocess, False)

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off", ""):
            return False
        return bool(value)

    def process(self, sta, grid=None, background=None):
        """站点→格点最近邻高斯插值。

        Args:
            sta: 站点数据。
            grid: 目标网格信息；缺省时从 ``background`` 取。
            background: 背景场。False 路径可选（远点填充）；True 路径必需。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场；``attrs`` 继承自 ``sta``。
        """
        # 与 IDW 相同的 grid/background 约定
        if self.reprocess and background is None:
            raise ValueError("reprocess=true 时必须提供 background 格点场")
        if grid is None:
            if background is None:
                raise ValueError("须提供 grid，或提供 background 以取网格")
            g0 = (
                meb.get_grid_of_data(background)
                if hasattr(meb, "get_grid_of_data")
                else meb.basicdata.get_grid_of_data(background)
            )
            grid = meb.basicdata.grid(g0.glon, g0.glat)

        sta1 = meb.sele_by_para(sta, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []
        half_r = float(self.halfR)

        for sta_slice in sta_list:
            data_name = meb.get_stadata_names(sta_slice)
            index0 = sta_slice.index[0]
            grid2 = meb.basicdata.grid(
                grid.glon,
                grid.glat,
                [sta_slice.loc[index0, "time"]],
                [int(sta_slice.loc[index0, "dtime"])],
                [int(sta_slice.loc[index0, "level"])],
                data_name,
            )

            if background is None:
                bg = meb.basicdata.grid_data(grid2)
            else:
                bg = InterpGgLinear(outer_value=self.outer_value).process(
                    background, grid2
                )
                if bg is None:
                    raise ValueError(
                        "背景场对齐失败：目标网格超出背景范围时请设置 outer_value"
                    )
            bg_dat = np.asarray(bg.values, dtype=float).flatten()

            if self.reprocess:
                # 偏差路径：末列改为 obs−bg；超 halfR 填 0（叠回后保留背景）
                sta_use = sta_slice.copy()
                bg_at_sta = meb.interp_gs_linear(bg, sta_slice)
                sta_use.iloc[:, -1] = sta_slice.iloc[:, -1] - bg_at_sta.iloc[:, -1]
                far_fill = 0.0
            else:
                # 绝对值：超 halfR 回退背景（无背景则为 0）
                sta_use = sta_slice
                far_fill = bg_dat

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

            # 每格点仅最近 1 站 × 高斯；halfR 同时作硬截断
            tree = cKDTree(xyz_sta)
            d, inds = tree.query(xyz_grid, k=1)
            input_dat = sta_use.iloc[:, -1].values
            w_gauss = np.exp(-(d / half_r) ** 2)
            dat = w_gauss * input_dat[inds]
            outside = d > half_r
            fill = far_fill if np.isscalar(far_fill) else far_fill
            dat = np.where(outside, fill, dat)
            dat = dat.astype(np.float32)

            if self.reprocess:
                # Δ 叠回背景 → 分析场
                grd_delta = meb.basicdata.grid_data(grid2, dat)
                grd = bg.copy()
                grd.values = grd.values + grd_delta.values
                grd.name = "data0"
            else:
                grd = meb.basicdata.grid_data(grid2, dat)
                grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        grd_all.attrs = copy.deepcopy(sta.attrs)
        return grd_all
