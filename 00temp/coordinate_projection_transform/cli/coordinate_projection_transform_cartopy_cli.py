# -*- coding: utf-8 -*-
"""兼容入口：等价于主 CLI ``backend=cartopy``（现已是主 CLI 默认）。

保留 ``cli=cartopy`` / 本模块 ``process``，避免旧调用断裂。
新代码请直接用 ``coordinate_projection_transform_cli.process``，
需要 iris 时传 ``backend=iris``。
"""
from __future__ import annotations

from typing import List

from .coordinate_projection_transform_cli import process as _process


def process(
    mode: str = None,
    backend: str = None,
    source_cube: str = None,
    projection_extent: List[float] = None,
    secant_latitudes: List[float] = None,
    grid_distance: float = None,
    lonlat_extent: List[float] = None,
    grid_spacing: float = None,
    regrid_mode: str = None,
    extrapolation_mode: str = None,
    config=None,
):
    """转发主 CLI；未显式指定时强制 ``backend=cartopy``。"""
    return _process(
        mode=mode,
        backend="cartopy" if backend is None else backend,
        source_cube=source_cube,
        projection_extent=projection_extent,
        secant_latitudes=secant_latitudes,
        grid_distance=grid_distance,
        lonlat_extent=lonlat_extent,
        grid_spacing=grid_spacing,
        regrid_mode=regrid_mode,
        extrapolation_mode=extrapolation_mode,
        config=config,
    )
