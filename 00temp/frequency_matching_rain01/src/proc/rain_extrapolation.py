# -*- coding: utf-8 -*-
"""
降水平流外推（``RainExtrapolation``）。

用光流得到的 (u, v) 对降水场做一步半拉格朗日后向平流：
从目标格点沿 ``-u·Δt, -v·Δt`` 回溯到源点取样。
"""
from __future__ import annotations

import numpy as np

from utils.types import GridData


class RainExtrapolation:
    """半拉格朗日降水位移。"""

    @staticmethod
    def simple_semi_lagrangian_in_angle(
        gd_uwnd: GridData,
        gd_vwnd: GridData,
        gd_rain: GridData,
        deta_time: float,
    ) -> GridData:
        """
        半拉格朗日平流（角度/经纬度网格上的简化形式）。

        Parameters
        ----------
        gd_uwnd / gd_vwnd :
            经向、纬向位移风速（与 ``deta_time`` 相乘后单位为度）。
        gd_rain :
            待平流降水场。
        deta_time :
            时间步长因子；业务中常取 ``1.0`` 表示一整步位移。

        Returns
        -------
        GridData
            平流后的降水场；源点越界处保留原值。
        """
        gd_output = gd_rain.copy_grid_data()
        # meshgrid 得到与 val[y,x] 一致的经纬度网格
        lon_grid, lat_grid = np.meshgrid(
            gd_output.lon, gd_output.lat, indexing="xy"
        )
        # 后向轨迹：源点 = 当前点 - 风 × Δt
        from_lon = lon_grid - gd_uwnd.val * deta_time
        from_lat = lat_grid - gd_vwnd.val * deta_time
        fallback = gd_rain.val
        sampled = gd_rain.interpolate_points(from_lon, from_lat, np.nan)
        gd_output.val = np.where(np.isnan(sampled), fallback, sampled)
        return gd_output
