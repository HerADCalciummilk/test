# -*- coding: utf-8 -*-
"""正交规则经纬网一阶面积加权（AreaWeighted）重网格核。

算法对齐 Iris ``iris.analysis.AreaWeighted`` / ``_area_weighted.py``：
先分别求源/目标一维格边重叠权重，再外积合成二维稀疏面积权重，
最后 ``data @ W.T`` 并按有效覆盖归一化。

球面：经度用弧度（可周期）；纬度边界取 ``sin(lat)`` 作面积因子。
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy.sparse import csr_array


def contiguous_bounds_1d(centers: np.ndarray, spacing: Optional[float] = None) -> np.ndarray:
    """由等距中心点生成 contiguous 格边（长度 = n+1）。"""
    centers = np.asarray(centers, dtype=np.float64).reshape(-1)
    if centers.size < 1:
        raise ValueError("centers 不能为空")
    if centers.size == 1:
        d = 1.0 if spacing is None else float(spacing)
        return np.array([centers[0] - 0.5 * d, centers[0] + 0.5 * d], dtype=np.float64)
    if spacing is None:
        d = float(centers[1] - centers[0])
    else:
        d = float(spacing)
    edges = np.empty(centers.size + 1, dtype=np.float64)
    edges[0] = centers[0] - 0.5 * d
    edges[1:-1] = 0.5 * (centers[:-1] + centers[1:])
    edges[-1] = centers[-1] + 0.5 * d
    return edges


def _get_coord_to_coord_matrix_info(
    src_bounds: np.ndarray,
    tgt_bounds: np.ndarray,
    circular: bool = False,
    mod: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """一维源/目标格边重叠权重（对齐 Iris）。

    返回 ``(weights, tgt_indices, src_indices)``。
    """
    src_bounds = np.asarray(src_bounds, dtype=np.float64).reshape(-1)
    tgt_bounds = np.asarray(tgt_bounds, dtype=np.float64).reshape(-1)
    m = len(tgt_bounds) - 1
    n = len(src_bounds) - 1
    if m < 1 or n < 1:
        raise ValueError("bounds 长度须至少为 2")

    src_decreasing = src_bounds[0] > src_bounds[1]
    tgt_decreasing = tgt_bounds[0] > tgt_bounds[1]
    if src_decreasing:
        src_bounds = src_bounds[::-1]
    if tgt_decreasing:
        tgt_bounds = tgt_bounds[::-1]

    if circular:
        if mod is None or mod <= 0:
            raise ValueError("circular=True 时须提供正的 mod")
        adjust = (tgt_bounds.min() - src_bounds.min()) // mod
        src_bounds = src_bounds + (mod * adjust)
        src_bounds = np.append(src_bounds, src_bounds + mod)
        nn = (2 * n) + 1
    else:
        nn = n

    i = max(int(np.searchsorted(tgt_bounds, src_bounds[0], side="right") - 1), 0)
    j = max(int(np.searchsorted(src_bounds, tgt_bounds[0], side="right") - 1), 0)

    data = []
    rows = []
    cols = []
    floor = max(tgt_bounds[i], src_bounds[j])
    while i < m and j < nn:
        rows.append(i)
        cols.append(j)
        if tgt_bounds[i + 1] < src_bounds[j + 1]:
            next_floor = tgt_bounds[i + 1]
            next_i = i + 1
        elif tgt_bounds[i + 1] == src_bounds[j + 1]:
            next_floor = tgt_bounds[i + 1]
            next_i = i + 1
            j += 1
        else:
            next_floor = src_bounds[j + 1]
            next_i = i
            j += 1
        denom = tgt_bounds[i + 1] - tgt_bounds[i]
        weight = 0.0 if denom == 0 else (next_floor - floor) / denom
        data.append(weight)
        i = next_i
        floor = next_floor

    data = np.asarray(data, dtype=np.float64)
    rows = np.asarray(rows, dtype=np.intp)
    cols = np.asarray(cols, dtype=np.intp)

    if circular:
        oob = np.where(cols == n)[0]
        data = np.delete(data, oob)
        rows = np.delete(rows, oob)
        cols = np.delete(cols, oob)
        cols = cols % (n + 1)

    if src_decreasing:
        cols = n - cols - 1
    if tgt_decreasing:
        rows = m - rows - 1
    return data, rows, cols


def _combine_xy_weights(x_info, y_info, src_shape, tgt_shape) -> csr_array:
    """将 X/Y 一维权重外积成 flatten(y,x) 稀疏矩阵（行=目标，列=源）。"""
    x_src, y_src = src_shape
    x_tgt, y_tgt = tgt_shape
    src_size = x_src * y_src
    tgt_size = x_tgt * y_tgt
    x_weight, x_rows, x_cols = x_info
    y_weight, y_rows, y_cols = y_info

    xy_weight = (y_weight[:, np.newaxis] * x_weight[np.newaxis, :]).ravel()
    xy_rows = ((y_rows[:, np.newaxis] * x_tgt) + x_rows[np.newaxis, :]).ravel()
    xy_cols = ((y_cols[:, np.newaxis] * x_src) + x_cols[np.newaxis, :]).ravel()
    return csr_array((xy_weight, (xy_rows, xy_cols)), shape=(tgt_size, src_size))


def build_area_weighted_weights(
    src_lon_bounds: np.ndarray,
    src_lat_bounds: np.ndarray,
    tgt_lon_bounds: np.ndarray,
    tgt_lat_bounds: np.ndarray,
    *,
    spherical: bool = True,
    circular_lon: bool = False,
) -> csr_array:
    """由源/目标经纬格边构建面积加权稀疏矩阵。

    矩阵形状 ``(n_tgt_lat * n_tgt_lon, n_src_lat * n_src_lon)``，
    数组约定为 ``(lat, lon)`` flatten 行优先（与 ``arr.reshape(-1)`` 一致）。
    """
    src_lon_bounds = np.asarray(src_lon_bounds, dtype=np.float64)
    src_lat_bounds = np.asarray(src_lat_bounds, dtype=np.float64)
    tgt_lon_bounds = np.asarray(tgt_lon_bounds, dtype=np.float64)
    tgt_lat_bounds = np.asarray(tgt_lat_bounds, dtype=np.float64)

    if spherical:
        deg2rad = np.pi / 180.0
        src_x = src_lon_bounds * deg2rad
        tgt_x = tgt_lon_bounds * deg2rad
        src_y = np.sin(src_lat_bounds * deg2rad)
        tgt_y = np.sin(tgt_lat_bounds * deg2rad)
        mod = 2.0 * np.pi if circular_lon else None
    else:
        src_x, tgt_x = src_lon_bounds, tgt_lon_bounds
        src_y, tgt_y = src_lat_bounds, tgt_lat_bounds
        mod = 360.0 if circular_lon else None

    # Iris 内部 src_shape/tgt_shape 为 (nx, ny)；最终 flatten 按 (y, x)
    src_shape = (len(src_lon_bounds) - 1, len(src_lat_bounds) - 1)
    tgt_shape = (len(tgt_lon_bounds) - 1, len(tgt_lat_bounds) - 1)
    x_info = _get_coord_to_coord_matrix_info(
        src_x, tgt_x, circular=circular_lon, mod=mod
    )
    y_info = _get_coord_to_coord_matrix_info(src_y, tgt_y)
    return _combine_xy_weights(x_info, y_info, src_shape, tgt_shape)


def apply_area_weighted(
    data_lat_lon: np.ndarray,
    weights: csr_array,
    tgt_nlat: int,
    tgt_nlon: int,
    *,
    mdtol: float = 1.0,
    fill_value: Optional[float] = None,
) -> np.ndarray:
    """对 ``(..., lat, lon)`` 场应用面积加权；末两维为水平。

    Parameters
    ----------
    mdtol :
        缺测/域外容差，同 Iris：覆盖比例低于 ``1-mdtol`` 的目标点视为无效。
    fill_value :
        无效目标点填充；``None`` 时用 NaN。
    """
    if not (0.0 <= float(mdtol) <= 1.0):
        raise ValueError("mdtol 须在 [0, 1]")
    data = np.asarray(data_lat_lon, dtype=np.float64)
    if data.ndim < 2:
        raise ValueError("data 至少为二维 (lat, lon)")
    src_nlat, src_nlon = data.shape[-2:]
    tgt_shape = (int(tgt_nlat), int(tgt_nlon))
    extra = data.shape[:-2]
    flat = data.reshape(-1, src_nlat * src_nlon)

    # 有效源贡献比例
    valid = np.isfinite(flat).astype(np.float64)
    filled = np.where(np.isfinite(flat), flat, 0.0)
    weight_sums = valid @ weights.T
    inbound_sums = np.ones((1, src_nlat * src_nlon), dtype=np.float64) @ weights.T

    mdtol_use = max(float(mdtol), 1e-8)
    # Iris 默认：目标格点须几乎完全落在源域内，且有效贡献够
    tgt_ok = (weight_sums > 1.0 - mdtol_use) & (inbound_sums > 1.0 - 1e-8)
    tgt_ok = np.broadcast_to(tgt_ok, weight_sums.shape)

    result = filled @ weights.T
    # 按有效源覆盖归一化（避免掩膜源把总量拉低）
    norm = np.ones_like(result)
    mask_ok = tgt_ok & (weight_sums > 0)
    norm[mask_ok] = 1.0 / weight_sums[mask_ok]
    result = result * norm

    fill = np.nan if fill_value is None else float(fill_value)
    result = np.where(tgt_ok, result, fill)
    return result.reshape(extra + tgt_shape).astype(np.float32)
