"""风的合成诊断量：由 u、v 分量计算风速与风向。

两个插件均以 meb 标准网格作为输入输出，文件读写由 cli 负责。
"""

from __future__ import annotations

from typing import Union

import numpy as np
import xarray as xr

from base_plugin import BasePlugin
from grid_utils import check_griddata, rebuild_griddata

# 静风判定阈值，单位 m/s
CALM_SPEED = 0.3


def wind_speed(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """由 u、v 分量计算合成风速，单位与输入一致。"""
    return np.sqrt(np.square(u) + np.square(v))


def wind_direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """计算气象风向（风的来向），单位为度，正北为 0 且顺时针增加。"""
    degrees = np.degrees(np.arctan2(v, u))
    return np.mod(270.0 - degrees, 360.0)


def gust_factor(speed: np.ndarray, factor: float = 1.35) -> np.ndarray:
    return np.asarray(speed) * factor


class ComputeWindSpeed(BasePlugin):
    """合成风速插件。"""

    def __init__(self) -> None:
        """初始化插件。"""
        super().__init__()

    def process(self, u: xr.DataArray, v: xr.DataArray) -> xr.DataArray:
        """计算合成风速网格。

        Args:
            u: 纬向风分量，meb 标准网格。
            v: 经向风分量，meb 标准网格。

        Returns:
            风速网格，member 为 wind_speed，单位 m/s。
        """
        u_grid = check_griddata(u, "u 风分量")
        v_grid = check_griddata(v, "v 风分量")

        speed = wind_speed(np.asarray(u_grid), np.asarray(v_grid))
        # 静风阈值：风速低于 0.5 m/s 视为静风，置 0
        speed = np.where(speed < CALM_SPEED, 0.0, speed)
        return rebuild_griddata(speed, u_grid, "m/s", "wind_speed")


class ComputeWindDirection(BasePlugin):
    """合成风向插件。"""

    def __init__(self) -> None:
        """初始化插件。"""
        super().__init__()

    def process(self, u: Union[xr.DataArray, np.ndarray],
                v: Union[xr.DataArray, np.ndarray]) -> xr.DataArray:
        """计算合成风向网格。

        Args:
            u: 纬向风分量，meb 标准网格或裸数组。
            v: 经向风分量，meb 标准网格或裸数组。

        Returns:
            风向网格，member 为 wind_direction，单位 degree。
        """
        if isinstance(u, xr.DataArray):
            u_grid = check_griddata(u, "u 风分量")
            v_grid = check_griddata(v, "v 风分量")
            direction = wind_direction(np.asarray(u_grid), np.asarray(v_grid))
            return rebuild_griddata(direction, u_grid, "degree", "wind_direction")

        # 兼容早期直接传 numpy 数组的调用方
        return wind_direction(np.asarray(u), np.asarray(v))
