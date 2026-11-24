# -*- coding: utf-8 -*-
"""极坐标门点 → 经纬规则网格（参考 cinrad.grid.grid_2d）。

仅依赖 numpy + scipy（或 pykdtree），不依赖 cinrad。
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

try:
    from pykdtree.kdtree import KDTree
except ImportError:  # pragma: no cover
    from scipy.spatial import KDTree


class KDResampler:
    """KD 树最近邻重采样；超出 ``roi`` 的目标点填 NaN。"""

    def __init__(
        self,
        data: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        roi: float = 0.02,
    ):
        x_ravel = np.asarray(x, dtype=np.float64).ravel()
        y_ravel = np.asarray(y, dtype=np.float64).ravel()
        self.tree = KDTree(np.column_stack((x_ravel, y_ravel)))
        self.data = np.asarray(data, dtype=np.float64).ravel()
        self.roi = float(roi)

    def map_data(self, x_out: np.ndarray, y_out: np.ndarray) -> np.ndarray:
        out_coords = np.column_stack(
            (
                np.asarray(x_out, dtype=np.float64).ravel(),
                np.asarray(y_out, dtype=np.float64).ravel(),
            )
        )
        _, indices = self.tree.query(out_coords, distance_upper_bound=self.roi)
        invalid_mask = indices == self.tree.n
        indices = indices.copy()
        indices[invalid_mask] = 0
        data = self.data[indices]
        data = data.astype(np.float64, copy=False)
        data[invalid_mask] = np.nan
        return data.reshape(np.asarray(x_out).shape)


def grid_2d(
    data: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    x_out: Optional[np.ndarray] = None,
    y_out: Optional[np.ndarray] = None,
    resolution: Sequence[int] = (1000, 1000),
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """将极坐标门点场插值到经纬规则网格。

    Parameters
    ----------
    data :
        径向数据，形状 ``(naz, ngate)``。
    x, y :
        各库经度 / 纬度，与 ``data`` 同形。
    x_out, y_out :
        目标经 / 纬一维轴；缺省时按数据范围与 ``resolution`` 均匀生成。
    resolution :
        ``(nx, ny)``，仅在未给出 ``x_out`` / ``y_out`` 时使用。

    Returns
    -------
    result, x_out, y_out
        插值场 ``(ny, nx)`` 与经纬轴。
    """
    nx, ny = int(resolution[0]), int(resolution[1])
    x_arr = np.asarray(x, dtype=np.float64)
    y_arr = np.asarray(y, dtype=np.float64)
    if x_out is None:
        x_out = np.linspace(float(np.nanmin(x_arr)), float(np.nanmax(x_arr)), nx)
    if y_out is None:
        y_out = np.linspace(float(np.nanmin(y_arr)), float(np.nanmax(y_arr)), ny)
    t_x, t_y = np.meshgrid(x_out, y_out)
    result = KDResampler(data, x_arr, y_arr).map_data(t_x, t_y)
    return result, np.asarray(x_out), np.asarray(y_out)


__all__ = ["KDResampler", "grid_2d"]
