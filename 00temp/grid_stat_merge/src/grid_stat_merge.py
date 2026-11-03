# -*- coding: utf-8 -*-
"""
格站融合（Grid-Stat Merge）通用算法插件。

核心：用站点相对格点的偏差，按高斯权重订正网格场。

    融合格点 = 原格点 + 偏差场

函数入口
--------
- ``do_gs_merge``           主融合
- ``interp_sg_diffuse``     站点铺网 + 热传导入口
- ``diffuse_values``        热传导扩散

插件入口
--------
- ``GridStatMergePlugin``   可调用；``plugin(grd, sta)``
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy.ndimage import convolve, gaussian_filter

import meteva.base as meb

from utils.base_plugin import BasePlugin

try:
    import utils.common_func as cf
    _HAS_CF = hasattr(cf, "gaussian_2d")
except Exception:
    cf = None
    _HAS_CF = False


def _interp_gs_linear(grd, sta):
    """格点→站点线性插值；部分 meteva 版本 ``interp_gs_linear`` 异常时回退 meteva_base。"""
    try:
        return meb.interp_gs_linear(grd, sta)
    except TypeError:
        import meteva_base as mb
        return mb.interp_gs_linear(grd, sta)


def gaussian_2d(x, y, mean_x, mean_y, cov, scale_factor=1.0):
    """
    二维高斯权重核。

    优先使用 ``utils.common_func.gaussian_2d``（若可用），否则本地实现，
    保证与调用 ``gaussian_2d(x1, x1, 0, 0, SIGMA, scale_factor=1e6)`` 一致的接口。

    输入
    ----
    x, y : 1d array
        相对坐标轴（通常为 ``arange(-R, R+1)``）。
    mean_x, mean_y : float
        均值中心。
    cov : ndarray, shape (2, 2)
        协方差矩阵。
    scale_factor : float
        整体放大系数。

    输出
    ----
    w : ndarray, shape (len(y), len(x))
        二维权重场。
    """
    if _HAS_CF:
        return cf.gaussian_2d(x, y, mean_x, mean_y, cov, scale_factor=scale_factor)

    X, Y = np.meshgrid(x, y)
    dx = X - mean_x
    dy = Y - mean_y
    inv = np.linalg.inv(np.asarray(cov, dtype=float))
    q = inv[0, 0] * dx * dx + (inv[0, 1] + inv[1, 0]) * dx * dy + inv[1, 1] * dy * dy
    return scale_factor * np.exp(-0.5 * q)


def diffuse_values(
    matrix: np.ndarray,
    fg_matrix: Optional[np.ndarray] = None,
    num_iterations: int = 20,
    alpha: float = 0.3,
    tol: float = 1e-4,
    patience: int = 5,
) -> np.ndarray:
    """
    热传导扩散：固定散点值，迭代平滑整场（去牛眼）。

    输入
    ----
    matrix : ndarray (ny, nx)
        散点落网场；非零点在迭代中保持不变。
    fg_matrix : ndarray (ny, nx), optional
        初猜场；None 时对非零点 cubic 插值生成。
    num_iterations, alpha, tol, patience :
        迭代与 early-stop 参数。

    输出
    ----
    ndarray (ny, nx)
        扩散后的二维场。
    """
    nrows, ncols = matrix.shape
    x = np.arange(ncols)
    y = np.arange(nrows)
    xv, yv = np.meshgrid(x, y)

    points = np.column_stack(np.where(matrix != 0))
    values = matrix[matrix != 0]

    if fg_matrix is None:
        fg_matrix = griddata(points, values, (yv, xv), method="cubic", fill_value=0)

    point_mask = (matrix != 0)
    fg_matrix = np.array(fg_matrix, copy=True)
    fg_matrix[point_mask] = matrix[point_mask]

    diffused_matrix = fg_matrix.copy()
    kernel = np.array([[0, 1, 0],
                       [1, 0, 1],
                       [0, 1, 0]], dtype=float) * 0.25

    last_change = np.inf
    no_improvement_count = 0

    for it in range(num_iterations):
        neighbor_avg = convolve(diffused_matrix, kernel, mode="nearest")
        new_matrix = diffused_matrix + alpha * (neighbor_avg - diffused_matrix)
        new_matrix = gaussian_filter(new_matrix, sigma=10.0)
        new_matrix[point_mask] = matrix[point_mask]

        current_change = np.max(np.abs(new_matrix - diffused_matrix))
        if current_change < last_change * (1 - tol):
            last_change = current_change
            no_improvement_count = 0
        else:
            no_improvement_count += 1
            if no_improvement_count >= patience:
                print(f"Early stopping at iteration {it + 1}")
                break
        diffused_matrix = new_matrix

    return diffused_matrix


def interp_sg_diffuse(
    fg_matrix: np.ndarray,
    s_val: np.ndarray,
    s_lons: np.ndarray,
    s_lats: np.ndarray,
    s_alts,
    nor: float,
    sou: float,
    wst: float,
    est: float,
    dlon: float,
    dlat: float,
    hf_eq_iter_nums: int,
):
    """
    站点值落规则网格，再热传导扩散。

    输入
    ----
    fg_matrix : ndarray (ny, nx)
        偏差初猜场。
    s_val, s_lons, s_lats : ndarray (nsta,)
        站点值与经纬度。
    s_alts :
        原接口保留，当前未使用。
    nor, sou, wst, est, dlon, dlat :
        网格范围与格距。
    hf_eq_iter_nums : int
        扩散迭代次数。

    输出
    ----
    ndarray (ny, nx) 或 int
        扩散场；若 ``sum(|s_val|) < 10`` 返回 0（原逻辑）。
    """
    if np.sum(np.abs(s_val)) < 10:
        return 0

    nrows = int((nor - sou) / dlat + 1.5)
    ncols = int((est - wst) / dlon + 1.5)
    gmat = np.zeros((nrows, ncols), dtype=np.float32)

    idx_rows = np.maximum(
        np.minimum(((s_lats - sou) / dlat + 0.5).astype(np.int32), nrows - 1), 0)
    # 原实现分母为 dlat（非 dlon），保持不变
    idx_cols = np.maximum(
        np.minimum(((s_lons - wst) / dlat + 0.5).astype(np.int32), ncols - 1), 0)
    gmat[idx_rows, idx_cols] = s_val

    return diffuse_values(gmat, fg_matrix, num_iterations=hf_eq_iter_nums)


def do_gs_merge(
    ifcst_g,
    ifcst_s: pd.DataFrame,
    R: float = 200.0,
    domain: Optional[Sequence[float]] = None,
    terr_mat=None,
    b_use_heatflux_equation: bool = False,
    hf_eq_iter_nums: Optional[int] = None,
    sta_val_col: str = "val",
    sta_lon_col: str = "lon",
    sta_lat_col: str = "lat",
    copy_grid: bool = True,
):
    """
    格站融合主算法。

        融合格点 = 原格点 + 偏差场
        bias = 站点值 − 格点插到站
        偏差场 = 各站 bias 的高斯加权平均（可选地形掩膜 / 热传导）

    输入
    ----
    ifcst_g : meteva 格点场
        待订正网格预报。
    ifcst_s : DataFrame
        站点数据，至少含经纬与取值列（默认 lon/lat/val）。
    R : float
        误差传播半径（索引单位）；水平影响约 ``R*0.01`` 度，``σ≈0.35*R``。
    domain : sequence of 6 floats, optional
        ``(sou, nor, wst, est, dlon, dlat)``。
        None 时从 ``ifcst_g`` 网格自动推断。
    terr_mat : meteva 格点场, optional
        地形；提供则仅在 |Δh|<100 m 区域传播偏差。
    b_use_heatflux_equation : bool
        是否对偏差场做热传导平滑。
    hf_eq_iter_nums : int, optional
        热传导迭代次数（开启时需要）。
    sta_val_col, sta_lon_col, sta_lat_col : str
        站点列名。
    copy_grid : bool
        True 时先拷贝格点再写回，避免改动入参对象。

    输出
    ----
    ifcst_g_out : meteva 格点场
        订正后的网格预报。
    """
    if copy_grid:
        ifcst_g = ifcst_g.copy(deep=True)

    sta = ifcst_s.copy()
    if sta_val_col != "val" and "val" not in sta.columns:
        sta = sta.rename(columns={sta_val_col: "val"})
    if sta_lon_col != "lon" and "lon" not in sta.columns:
        sta = sta.rename(columns={sta_lon_col: "lon"})
    if sta_lat_col != "lat" and "lat" not in sta.columns:
        sta = sta.rename(columns={sta_lat_col: "lat"})

    if domain is None:
        g0 = meb.get_grid_of_data(ifcst_g) if hasattr(meb, "get_grid_of_data") else None
        if g0 is None:
            import meteva
            g0 = meteva.base.basicdata.get_grid_of_data(ifcst_g)
        sou, nor = float(g0.slat), float(g0.elat)
        wst, est = float(g0.slon), float(g0.elon)
        dlon, dlat = float(g0.dlon), float(g0.dlat)
    else:
        sou, nor, wst, est, dlon, dlat = [float(x) for x in domain]

    # step1: bias = 站 − 格点插值到站
    g2s = _interp_gs_linear(ifcst_g, sta)
    data0_col = "data0" if "data0" in g2s.columns else g2s.columns[-1]
    sta["bias"] = sta["val"].to_numpy(dtype=float) - g2s[data0_col].to_numpy(dtype=float)

    # step2: 高斯传播
    bias_mat = np.zeros_like(np.squeeze(ifcst_g.values), dtype=float)
    w_mat = np.zeros_like(bias_mat)

    slons = np.round(sta["lon"].to_numpy(dtype=float), decimals=2)
    slats = np.round(sta["lat"].to_numpy(dtype=float), decimals=2)
    bias = sta["bias"].to_numpy(dtype=float)

    sm_sou = np.round(np.maximum(slats - R * 0.01, sou), decimals=2)
    sm_nor = np.round(np.minimum(slats + R * 0.01, nor), decimals=2)
    sm_wst = np.round(np.maximum(slons - R * 0.01, wst), decimals=2)
    sm_est = np.round(np.minimum(slons + R * 0.01, est), decimals=2)

    idx_sm_s = ((sm_sou - (slats - R * 0.01)) / dlat + 0.5).astype(np.int32)
    idx_sm_n = ((sm_nor - (slats - R * 0.01)) / dlat + 0.5).astype(np.int32)
    idx_sm_w = ((sm_wst - (slons - R * 0.01)) / dlon + 0.5).astype(np.int32)
    idx_sm_e = ((sm_est - (slons - R * 0.01)) / dlon + 0.5).astype(np.int32)

    idx_lm_s = ((sm_sou - sou) / dlat + 0.5).astype(np.int32)
    idx_lm_n = ((sm_nor - sou) / dlat + 0.5).astype(np.int32)
    idx_lm_w = ((sm_wst - wst) / dlon + 0.5).astype(np.int32)
    idx_lm_e = ((sm_est - wst) / dlon + 0.5).astype(np.int32)

    x1 = np.arange(-R, R + 1, 1)
    isig = (R * 0.35) ** 2
    sigma = np.array([[isig, 0.0], [0.0, isig]])
    w_basic = gaussian_2d(x1, x1, 0, 0, sigma, scale_factor=1e6)

    if terr_mat is not None:
        hgt_s = _interp_gs_linear(terr_mat, sta)
        hgt_col = "data0" if "data0" in hgt_s.columns else hgt_s.columns[-1]
        shgts = hgt_s[hgt_col].to_numpy(dtype=float)
        _terr = np.squeeze(np.asarray(terr_mat.values, dtype=float))
    else:
        shgts = None
        _terr = None

    for i in range(len(slons)):
        if (not np.isfinite(bias[i])) or (np.abs(bias[i]) > 1000):
            continue

        rs, re = int(idx_lm_s[i]), int(idx_lm_n[i]) + 1
        cs, ce = int(idx_lm_w[i]), int(idx_lm_e[i]) + 1
        wr0, wr1 = int(idx_sm_s[i]), int(idx_sm_n[i]) + 1
        wc0, wc1 = int(idx_sm_w[i]), int(idx_sm_e[i]) + 1
        if re <= rs or ce <= cs or wr1 <= wr0 or wc1 <= wc0:
            continue
        # 贴边时格点窗与高斯窗尺寸可能差 1，取交集
        nr = min(re - rs, wr1 - wr0, bias_mat.shape[0] - rs, w_basic.shape[0] - wr0)
        nc = min(ce - cs, wc1 - wc0, bias_mat.shape[1] - cs, w_basic.shape[1] - wc0)
        if nr <= 0 or nc <= 0:
            continue
        re, ce = rs + nr, cs + nc
        wr1, wc1 = wr0 + nr, wc0 + nc

        if _terr is not None:
            istat_dhgt = _terr[rs:re, cs:ce] - shgts[i]
            mask = (np.abs(istat_dhgt) < 100).astype(np.int32)
            _iw = w_basic[wr0:wr1, wc0:wc1] * mask
        else:
            _iw = w_basic[wr0:wr1, wc0:wc1]

        bias_mat[rs:re, cs:ce] += bias[i] * _iw
        w_mat[rs:re, cs:ce] += _iw

    w_mat += 1e-6
    bias_mat /= w_mat

    if b_use_heatflux_equation:
        if hf_eq_iter_nums is None:
            raise ValueError("开启热传导时必须提供 hf_eq_iter_nums")
        bias_mat = interp_sg_diffuse(
            bias_mat, bias, slons, slats, None,
            nor, sou, wst, est, dlon, dlat, hf_eq_iter_nums,
        )

    bias_mat = np.expand_dims(bias_mat, axis=(0, 1, 2, 3))
    ifcst_g.values = ifcst_g.values + bias_mat
    return ifcst_g


# 兼容旧函数名
def do_gs_merge_default_ikey(ifcst_g, ifcst_s, R, b_use_heatflux_equation,
                             hf_eq_iter_nums=None, domain=None, terr_mat=None, **kwargs):
    """兼容旧名；推荐使用 ``do_gs_merge`` / ``GridStatMergePlugin``。"""
    return do_gs_merge(
        ifcst_g, ifcst_s,
        R=R,
        domain=domain,
        terr_mat=terr_mat,
        b_use_heatflux_equation=b_use_heatflux_equation,
        hf_eq_iter_nums=hf_eq_iter_nums,
        **kwargs,
    )


class GridStatMergePlugin(BasePlugin):
    """
    可调用格站融合插件。

    用法::

        plugin = GridStatMergePlugin(
            R=200,
            domain=(0, 60, 70, 140, 0.1, 0.1),  # sou,nor,wst,est,dlon,dlat；可省略由格点推断
            b_use_heatflux_equation=False,
        )
        grd_out = plugin(grd_in, sta_df)
        # 等价
        grd_out = plugin.process(grd_in, sta_df)
    """

    def __init__(
        self,
        R: float = 200.0,
        domain: Optional[Sequence[float]] = None,
        terr_mat=None,
        b_use_heatflux_equation: bool = False,
        hf_eq_iter_nums: Optional[int] = None,
        sta_val_col: str = "val",
        sta_lon_col: str = "lon",
        sta_lat_col: str = "lat",
        copy_grid: bool = True,
    ):
        self.R = R
        self.domain = domain
        self.terr_mat = terr_mat
        self.b_use_heatflux_equation = b_use_heatflux_equation
        self.hf_eq_iter_nums = hf_eq_iter_nums
        self.sta_val_col = sta_val_col
        self.sta_lon_col = sta_lon_col
        self.sta_lat_col = sta_lat_col
        self.copy_grid = copy_grid

    def process(self, ifcst_g, ifcst_s: pd.DataFrame, **kwargs):
        """
        输入
        ----
        ifcst_g : meteva 格点场
        ifcst_s : DataFrame 站点

        输出
        ----
        订正后的 meteva 格点场
        """
        return do_gs_merge(
            ifcst_g,
            ifcst_s,
            R=kwargs.get("R", self.R),
            domain=kwargs.get("domain", self.domain),
            terr_mat=kwargs.get("terr_mat", self.terr_mat),
            b_use_heatflux_equation=kwargs.get(
                "b_use_heatflux_equation", self.b_use_heatflux_equation),
            hf_eq_iter_nums=kwargs.get("hf_eq_iter_nums", self.hf_eq_iter_nums),
            sta_val_col=kwargs.get("sta_val_col", self.sta_val_col),
            sta_lon_col=kwargs.get("sta_lon_col", self.sta_lon_col),
            sta_lat_col=kwargs.get("sta_lat_col", self.sta_lat_col),
            copy_grid=kwargs.get("copy_grid", self.copy_grid),
        )
