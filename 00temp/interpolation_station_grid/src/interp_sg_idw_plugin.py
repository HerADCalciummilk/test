# -*- coding: utf-8 -*-
"""站点→格点反距离权重插值（IDW），可选背景与高斯衰减。

接口：``process(sta, grid=None, background=None)``。

- ``reprocess=False``（默认）：插站点**绝对值**；``d > effectR`` 时回退背景
  （无背景则填 0）。须 ``grid``，或由 ``background`` 取网格（对齐 Cressman）。
- ``reprocess=True``：须 ``background``；插 ``obs - bg`` 再叠回。``grid`` 可省略，
  缺省时从 ``background`` 取网格（与 Cressman True 一样可只传背景）。

权重：

- ``gaussian=False``：``w = 1 / d^decrease``，``effectR`` 为硬截断半径。
- ``gaussian=True``：``w = (1 / d^decrease) * exp(-(d / effectR)^2)``，
  ``effectR`` 为高斯半径（原 InterpSgIdwDelta 权重）。
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


class InterpSgIdw(PostProcessingPlugin):
    """站点到格点 IDW 插值。

    - ``reprocess=False``：绝对值 IDW；超 ``effectR`` 用背景填（无背景填 0）；
      ``grid`` 与 ``background`` 至少其一。
    - ``reprocess=True``：偏差订正；须 ``background``；``grid`` 可省略（从背景取）。
    - ``gaussian=False``：纯 IDW；``gaussian=True``：IDW × 高斯。

    Parameters
    ----------
    effectR :
        纯 IDW 时为硬截断半径；高斯模式下为高斯衰减尺度（米量级）。
    nearNum :
        每个格点参与加权的近邻站点数。
    decrease :
        距离衰减指数 ``1 / d^decrease``。
    gaussian :
        是否乘高斯核。
    outer_value :
        背景场对齐越界填充，传给 ``InterpGgLinear``。
    reprocess :
        ``False``：绝对值 + 远点回退背景；``True``：偏差订正路径。
    """

    def __init__(
        self,
        effectR: Optional[int] = 1000,
        nearNum: Optional[int] = 8,
        decrease: Optional[int] = 2,
        gaussian: bool = False,
        outer_value: Optional[float] = None,
        reprocess: Any = False,
    ):
        self.effectR = effectR
        self.nearNum = nearNum
        self.decrease = decrease
        self.gaussian = bool(gaussian)
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
        """站点→格点插值。

        Args:
            sta: 站点数据。
            grid: 目标网格信息（``glon`` / ``glat`` 等）；缺省时从 ``background`` 取。
            background: 背景场。False 路径可选（远点填充）；True 路径必需。

        Returns:
            各 member/level/time/dtime 切片拼接后的格点场；``attrs`` 继承自 ``sta``。
        """
        # 参数：True 须背景；缺 grid 时从背景取水平网格
        if self.reprocess and background is None:
            raise ValueError("reprocess=true 时必须提供 background 格点场")
        if grid is None:
            if background is None:
                raise ValueError(
                    "须提供 grid，或提供 background 以取网格"
                )
            g0 = (
                meb.get_grid_of_data(background)
                if hasattr(meb, "get_grid_of_data")
                else meb.basicdata.get_grid_of_data(background)
            )
            grid = meb.basicdata.grid(g0.glon, g0.glat)

        sta1 = meb.sele_by_para(sta, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []
        for sta_slice in sta_list:
            data_name = meb.get_stadata_names(sta_slice)
            index0 = sta_slice.index[0]
            dtime = int(sta_slice.loc[index0, "dtime"])
            level = int(sta_slice.loc[index0, "level"])
            # 本切片输出网格信息（水平=grid，时间维=站点切片）
            grid2 = meb.basicdata.grid(
                grid.glon,
                grid.glat,
                [sta_slice.loc[index0, "time"]],
                [dtime],
                [level],
                data_name,
            )

            # 对齐背景到 grid2；无背景则全 0（绝对值远点填 0）
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
                # 偏差订正：插 obs−bg（末列），超距 Δ=0 → 叠回后保留背景
                sta_use = sta_slice.copy()
                bg_at_sta = meb.interp_gs_linear(bg, sta_slice)
                sta_use.iloc[:, -1] = sta_slice.iloc[:, -1] - bg_at_sta.iloc[:, -1]
                far_fill = 0.0
            else:
                # 绝对值：超 effectR 回退背景场值
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
            tree = cKDTree(xyz_sta)
            near_num = self.nearNum if self.nearNum <= len(sta_use.index) else len(sta_use.index)
            d, inds = tree.query(xyz_grid, k=near_num)

            # 插值用末列；effectR：纯 IDW 硬截断 / 高斯模式下为高斯尺度
            if near_num > 1:
                d = d + 1e-6
                w_idw = 1.0 / d ** self.decrease
                input_dat = sta_use.values[:, -1]
                if self.gaussian:
                    w_gauss = np.exp(-(d / self.effectR) ** 2)
                    dat = np.sum(w_idw * w_gauss * input_dat[inds], axis=1) / np.sum(
                        w_idw, axis=1
                    )
                else:
                    dat = np.sum(w_idw * input_dat[inds], axis=1) / np.sum(w_idw, axis=1)
                outside = d[:, 0] > self.effectR
                fill = far_fill if np.isscalar(far_fill) else far_fill
                dat = np.where(outside, fill, dat)
            else:
                input_dat = sta_use.iloc[:, -1].values
                if self.gaussian:
                    w_gauss = np.exp(-(d / self.effectR) ** 2)
                    dat = w_gauss * input_dat[inds]
                else:
                    dat = input_dat[inds]
                outside = d[:] > self.effectR
                fill = far_fill if np.isscalar(far_fill) else far_fill
                dat = np.where(outside, fill, dat)

            dat = dat.astype(np.float32)
            if self.reprocess:
                # Δ 叠回对齐后的背景 → 分析场
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
