# -*- coding: utf-8 -*-
"""规则经纬度网格。插值和 MICAPS / NetCDF 读写共用。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridConfig:
    """描述规则经纬度网格。"""

    lat_start: float
    lon_start: float
    lat_end: float
    lon_end: float
    dlat: float
    dlon: float
    num_x: int
    num_y: int
