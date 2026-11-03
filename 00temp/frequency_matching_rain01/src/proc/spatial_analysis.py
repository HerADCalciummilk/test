# -*- coding: utf-8 -*-
"""
空间分析与插值（``SpatialAnalysis``）。

提供降水专用 Cressman 多圈插值、站点硬约束填格，用于：
- 历史样本中由站点实况生成“订正目标格点场”（供光流）；
- 稀疏 UV 点插成风场；
- 订正站点场融合到模式背景后的格点产品。
"""
from __future__ import annotations

import math
import numpy as np

from utils.types import GridData, ScatterData


class SpatialAnalysis:
    """Cressman 插值与站点—格点约束。"""

    @staticmethod
    def grid_data_fix_by_scatter(sd_input_data: ScatterData, gd_output_data: GridData) -> None:
        """
        将站点值硬写入最近格点（原地修改 ``gd_output_data``）。

        同一格点多站时保留较大值，保证站点信息进入后续光流/检验场。
        """
        gd_flag = np.zeros_like(gd_output_data.val)
        for station in sd_input_data.sta_data:
            ix = int(round((station.lon - gd_output_data.lon_start) / gd_output_data.dlon))
            iy = int(round((station.lat - gd_output_data.lat_start) / gd_output_data.dlat))
            if 0 <= ix < gd_output_data.xn and 0 <= iy < gd_output_data.yn:
                if gd_flag[iy, ix] == 0.0 or station.val >= gd_output_data.val[iy, ix]:
                    gd_output_data.val[iy, ix] = station.val
                    gd_flag[iy, ix] = 1.0

    @staticmethod
    def _cressman_one_step_for_rain(
        sd_input_data: ScatterData,
        gd_background_data: GridData,
        distance_limit: float,
        number_limit: float = 1.0,
        smooth: float = 0.001,
        power_param: float = 2.0,
        rain_limit: float = 0.01,
    ) -> GridData:
        """
        单圈 Cressman（降水）：先算站点相对背景的增量，再把增量加权回网格。

        权重 ``w = 1 / (dist + smooth)^power``；有效点数不足或订正后过小雨则回退背景。
        """
        length = sd_input_data.length
        sd_from_background = sd_input_data.copy_scatter_data()
        scatter_data = sd_input_data.copy_scatter_data()
        influence_grid = int(distance_limit / gd_background_data.dlon)
        sd_from_background.clear_to_num(0.0)

        # —— 第一步：各站从背景场双线性邻域加权取样，得到“背景在站上的值” ——
        for n in range(length):
            station = sd_input_data.sta_data[n]
            ix = int((station.lon + 1e-5 - gd_background_data.lon_start) / gd_background_data.dlon)
            iy = int((station.lat + 1e-5 - gd_background_data.lat_start) / gd_background_data.dlat)
            xmin = max(ix - influence_grid, 0)
            xmax = min(ix + influence_grid, gd_background_data.xn - 1)
            ymin = max(iy - influence_grid, 0)
            ymax = min(iy + influence_grid, gd_background_data.yn - 1)
            lon_window = gd_background_data.lon[xmin : xmax + 1]
            lat_window = gd_background_data.lat[ymin : ymax + 1]
            dx = lon_window[:, None] - station.lon
            dy = lat_window[None, :] - station.lat
            dist = np.sqrt(dx * dx + dy * dy)
            mask = dist <= distance_limit
            if np.any(mask):
                weights = np.where(mask, 1.0 / np.power(dist + smooth, power_param), 0.0)
                # val[y,x]；weights 形状为 [wx, wy]，与背景切片相乘时需转置
                values = gd_background_data.val[ymin : ymax + 1, xmin : xmax + 1]
                weight_sum = weights.sum()
                sd_from_background.sta_data[n].val = (
                    float((weights.T * values).sum() / weight_sum)
                    if weight_sum >= 1e-5
                    else station.val
                )
            else:
                sd_from_background.sta_data[n].val = station.val

        # 站点增量 = 观测 − 背景取样
        for idx in range(length):
            scatter_data.sta_data[idx].val -= sd_from_background.sta_data[idx].val

        # —— 第二步：把增量加权铺回格点 ——
        grid1 = np.zeros_like(gd_background_data.val)  # Σ w·δ
        grid2 = np.zeros_like(gd_background_data.val)  # Σ w
        grid3 = np.zeros_like(gd_background_data.val)  # 有效站点数
        for station in scatter_data.sta_data:
            ix = int((station.lon - gd_background_data.lon_start) / gd_background_data.dlon)
            iy = int((station.lat - gd_background_data.lat_start) / gd_background_data.dlat)
            xmin = max(ix - influence_grid, 0)
            xmax = min(ix + influence_grid, gd_background_data.xn - 1)
            ymin = max(iy - influence_grid, 0)
            ymax = min(iy + influence_grid, gd_background_data.yn - 1)
            lon_window = gd_background_data.lon[xmin : xmax + 1]
            lat_window = gd_background_data.lat[ymin : ymax + 1]
            dx = lon_window[:, None] - station.lon
            dy = lat_window[None, :] - station.lat
            dist = np.sqrt(dx * dx + dy * dy)
            mask = dist <= distance_limit
            if not np.any(mask):
                continue
            weights = np.where(mask, 1.0 / np.power(dist + smooth, power_param), 0.0)
            grid1[ymin : ymax + 1, xmin : xmax + 1] += weights.T * station.val
            grid2[ymin : ymax + 1, xmin : xmax + 1] += weights.T
            grid3[ymin : ymax + 1, xmin : xmax + 1] += mask.T.astype(float)

        output = gd_background_data.copy_grid_data()
        valid = (grid2 >= 1e-5) & (grid3 >= number_limit)
        output.val = gd_background_data.val.copy()
        # 分析场 = 背景 + 增量估计
        output.val[valid] = grid1[valid] / grid2[valid] + gd_background_data.val[valid]
        # 过小雨回退背景，避免虚假小雨斑
        low_mask = valid & (output.val <= rain_limit)
        output.val[low_mask] = gd_background_data.val[low_mask]
        return output

    @staticmethod
    def gressman_interpolation_for_rain(
        sd_input_data: ScatterData,
        gd_background_data: GridData,
        distance_limits: list[float] | np.ndarray,
        num_limit: float = 1.0,
        smooth: float = 0.001,
        power_param: float = 2.0,
        rain_limit: float = 0.01,
    ) -> GridData:
        """多圈 Cressman：``distance_limits`` 由大到小逐圈迭代（如 1°, 0.5°, 0.25°, 0.1°）。"""
        output = gd_background_data.copy_grid_data()
        for distance in distance_limits:
            output = SpatialAnalysis._cressman_one_step_for_rain(
                sd_input_data,
                output,
                float(distance),
                num_limit,
                smooth,
                power_param,
                rain_limit,
            )
        return output

    @staticmethod
    def gressman_interpolation(
        sd_input_data: ScatterData,
        gd_background_data: GridData,
        distance_limits: list[float] | np.ndarray,
        num_limit: float = 1.0,
        smooth: float = 0.001,
        power_param: float = 2.0,
    ) -> GridData:
        """通用 Cressman（非降水专用）：``rain_limit`` 取极负，关闭小雨回退。"""
        return SpatialAnalysis.gressman_interpolation_for_rain(
            sd_input_data,
            gd_background_data,
            distance_limits,
            num_limit,
            smooth,
            power_param,
            -1e99,
        )
