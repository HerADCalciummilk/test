# -*- coding: utf-8 -*-
"""
光流位移估计（``OpticalFlow``）。

由多对「历史模式场 → 订正/实况场」估计局地位移矢量 (u, v)，再插值成格点风场，
供半拉格朗日平流使用。约束方程形式：``gx·u + gy·v ≈ -∂q/∂t``（亮度守恒离散）。
"""
from __future__ import annotations

import numpy as np

from utils.types import GridData, PointData, ScatterData
from .spatial_analysis import SpatialAnalysis


class OpticalFlow:
    """基于中心差分梯度与窗口最小二乘的光流求解。"""

    @staticmethod
    def _central_gradient_x(grid: GridData) -> GridData:
        """经向中心差分 ∂/∂lon；``val`` 布局为 ``[y, x]``。"""
        out = grid.copy_grid_data()
        out.clear_to_num(0.0)
        out.val[:, 1:-1] = (grid.val[:, 2:] - grid.val[:, :-2]) / (2.0 * grid.dlon)
        return out

    @staticmethod
    def _central_gradient_y(grid: GridData) -> GridData:
        """纬向中心差分 ∂/∂lat。"""
        out = grid.copy_grid_data()
        out.clear_to_num(0.0)
        out.val[1:-1, :] = (grid.val[2:, :] - grid.val[:-2, :]) / (2.0 * grid.dlat)
        return out

    @staticmethod
    def get_wind_from_optical_flow(
        gd_qpf_before: list[GridData],
        gd_qpf_next: list[GridData],
        min_window: list[list[float]],
        gd_output: list[GridData],
        rain_limit: float = 0.1,
        delta_rain_limit: float = 0.1,
        num_limit: int = 100,
    ) -> None:
        """
        估计光流风场，结果写回 ``gd_output[0]=u``、``gd_output[1]=v``（原地更新）。

        Parameters
        ----------
        gd_qpf_before / gd_qpf_next :
            成对的历史模式场与对应订正/实况格点场列表。
        min_window :
            ``[[dx_deg, dy_deg], ...]``，首元为分析窗口尺度（度）。
        rain_limit / delta_rain_limit :
            仅使用降水与时间变分超过阈值的格点参与方程。
        num_limit :
            单窗口有效方程数下限，不足则跳过该窗。
        """
        window = min_window[0]
        dx_count = max(int(window[0] / gd_qpf_before[0].dlon), 1)
        dy_count = max(int(window[1] / gd_qpf_before[0].dlat), 1)
        pdx = max(int(0.5 * dx_count), 1)
        pdy = max(int(0.5 * dy_count), 1)
        # 窗口中心网格索引（跳步采样，降低计算量）
        x_index = list(range(int(0.5 * dx_count) + 1, gd_qpf_before[0].xn - 1, pdx))
        y_index = list(range(int(0.5 * dy_count) + 1, gd_qpf_before[0].yn - 1, pdy))

        # 对每对场：时间平均梯度 + 时间差分
        grad_x, grad_y, delta = [], [], []
        for before, after in zip(gd_qpf_before, gd_qpf_next):
            gx = OpticalFlow._central_gradient_x(before)
            gx.add_val(OpticalFlow._central_gradient_x(after))
            gx.multi_val(0.5)
            gy = OpticalFlow._central_gradient_y(before)
            gy.add_val(OpticalFlow._central_gradient_y(after))
            gy.multi_val(0.5)
            d = after.copy_grid_data()
            d.sub_val(before)
            grad_x.append(gx.val)
            grad_y.append(gy.val)
            delta.append(d.val)

        before_vals = [g.val for g in gd_qpf_before]
        next_vals = [g.val for g in gd_qpf_next]
        u_points: list[PointData] = []
        v_points: list[PointData] = []

        for j_idx in y_index:
            j0, j1 = j_idx - pdy, j_idx + pdy + 1
            for i_idx in x_index:
                i0, i1 = i_idx - pdx, i_idx + pdx + 1
                rows = []
                rhs = []
                for level in range(len(gd_qpf_before)):
                    gx = grad_x[level][j0:j1, i0:i1]
                    gy = grad_y[level][j0:j1, i0:i1]
                    dv = delta[level][j0:j1, i0:i1]
                    # 只在有雨且时间变化显著的点上列方程
                    mask = (
                        (np.abs(dv) >= delta_rain_limit)
                        & (before_vals[level][j0:j1, i0:i1] >= rain_limit)
                        & (next_vals[level][j0:j1, i0:i1] >= rain_limit)
                    )
                    if np.any(mask):
                        rows.append(np.column_stack((gx[mask], gy[mask])))
                        rhs.append(-dv[mask])
                if not rhs:
                    continue
                a = np.vstack(rows)
                b = np.concatenate(rhs)
                if b.size < num_limit:
                    continue
                # 最小二乘解 (u, v)
                x, *_ = np.linalg.lstsq(a, b, rcond=None)
                lon = gd_qpf_before[0].lon_start + i_idx * gd_qpf_before[0].dlon
                lat = gd_qpf_before[0].lat_start + j_idx * gd_qpf_before[0].dlat
                u_points.append(PointData(f"u_{i_idx}_{j_idx}", float(lon), float(lat), float(x[0])))
                v_points.append(PointData(f"v_{i_idx}_{j_idx}", float(lon), float(lat), float(x[1])))

        if not u_points:
            gd_output[0].clear_to_num(0.0)
            gd_output[1].clear_to_num(0.0)
            return

        # 稀疏 UV 点 → 粗网格 Cressman → 再插回目标分辨率
        coarse_u = gd_output[0].mesh_val(
            gd_output[0].lon_start, gd_output[0].lon_end,
            gd_output[0].lat_start, gd_output[0].lat_end, window[0], window[1],
        )
        coarse_v = gd_output[1].mesh_val(
            gd_output[1].lon_start, gd_output[1].lon_end,
            gd_output[1].lat_start, gd_output[1].lat_end, window[0], window[1],
        )
        distance_limits = [4.0 * window[0], 2.0 * window[0], 1.0 * window[0]]
        grid_u = SpatialAnalysis.gressman_interpolation(ScatterData(u_points), coarse_u, distance_limits)
        grid_v = SpatialAnalysis.gressman_interpolation(ScatterData(v_points), coarse_v, distance_limits)
        gd_output[0] = grid_u.mesh_val(
            gd_output[0].lon_start, gd_output[0].lon_end,
            gd_output[0].lat_start, gd_output[0].lat_end,
            gd_output[0].dlon, gd_output[0].dlat,
        )
        gd_output[1] = grid_v.mesh_val(
            gd_output[1].lon_start, gd_output[1].lon_end,
            gd_output[1].lat_start, gd_output[1].lat_end,
            gd_output[1].dlon, gd_output[1].dlat,
        )
