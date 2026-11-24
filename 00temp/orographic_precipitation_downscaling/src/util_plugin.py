# -*- coding: utf-8 -*-
"""地形降水增强的算法辅助。

网格重采样仍在 ``src/utils/_grid.py``。这里转出饱和水汽压、邻域数值和
多尺度级联用的尺度展开。
"""
from __future__ import annotations

from typing import Optional

import xarray as xr

from orographic_precipitation_downscaling.src.utils._apply import (
    _extract_scalar_time_value,
    _nearest_time_index,
    _threshold_in_units,
    _to_datetime64,
)
from orographic_precipitation_downscaling.src.utils._numerics import (
    _regridded_adjacent_gradient,
    _square_neighbourhood_mean,
)
from orographic_precipitation_downscaling.src.utils._svp import calculate_svp_in_air

__all__ = [
    "_extract_scalar_time_value",
    "_nearest_time_index",
    "_threshold_in_units",
    "_to_datetime64",
    "_regridded_adjacent_gradient",
    "_square_neighbourhood_mean",
    "calculate_svp_in_air",
    "build_cascade_stages",
    "aggregate_orography",
]


def _parse_level_km(stages: str) -> list[float]:
    """把 ``20,5,1`` 解析成严格递减的分辨率列表，单位 km。"""
    text = str(stages).strip()
    if not text:
        raise ValueError("stages 不能为空，例如 20,5,1")
    try:
        levels = [float(item) for item in text.split(",") if item.strip()]
    except ValueError as exc:
        raise ValueError(f"stages 须为逗号分隔的公里数，收到 {stages!r}") from exc
    if len(levels) < 2:
        raise ValueError(f"stages 至少两档，收到 {stages!r}")
    if any(level <= 0 for level in levels):
        raise ValueError(f"stages 中的分辨率须为正，收到 {levels}")
    if any(nxt >= prev for prev, nxt in zip(levels, levels[1:])):
        raise ValueError(f"stages 须从粗到细严格递减，收到 {levels}")
    return levels


def _aggregate_factor(level_km: float, target_km: float) -> int:
    """目标地形聚合成该档网格时的整数倍数。"""
    ratio = float(level_km) / float(target_km)
    factor = int(round(ratio))
    if factor < 2 or abs(ratio - factor) > 1e-3:
        raise ValueError(
            f"分辨率 {level_km:g} km 不是目标 {target_km:g} km 的整数倍（≥2），无法聚合地形"
        )
    return factor


def aggregate_orography(orog_target: xr.DataArray, factor: int) -> xr.DataArray:
    """把目标地形按 factor×factor 块平均到更粗的网格。"""
    out = orog_target.coarsen(lat=factor, lon=factor, boundary="trim").mean()
    out.attrs = dict(orog_target.attrs)
    out.attrs["units"] = orog_target.attrs.get("units") or "m"
    out.name = orog_target.name or "orography"
    return out


def build_cascade_stages(
    stages: str,
    *,
    precip_spacing_km: float,
    zero_below: Optional[float] = None,
) -> list[dict]:
    """把尺度列表展开成每一次订正的设置。

    每次订正记下自己的降水格距和模式地形格距。
    ``zero_below`` 只赋给最粗一次。
    """
    from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
        RedistributeOrographicEnhancement,
    )

    levels = _parse_level_km(stages)
    if zero_below is None:
        zero_below = 0.0
    zero_below = float(zero_below)
    if zero_below < 0:
        raise ValueError(f"zero_below 须非负，收到 {zero_below}")
    if float(precip_spacing_km) <= 0:
        raise ValueError(f"precip_spacing_km 须为正，收到 {precip_spacing_km}")

    target_km = levels[-1]
    for level_km in levels[1:-1]:
        _aggregate_factor(level_km, target_km)

    specs = []
    for index, (model_orography_km, grid_km) in enumerate(zip(levels, levels[1:])):
        stage_precip_km = precip_spacing_km if index == 0 else model_orography_km
        specs.append(
            {
                "from_km": model_orography_km,
                "to_km": grid_km,
                "precip_spacing_km": stage_precip_km,
                "model_orography_spacing_km": model_orography_km,
                "smooth_radius": RedistributeOrographicEnhancement.doe_smooth_radius_cells(
                    stage_precip_km, grid_km
                ),
                "block_cells": RedistributeOrographicEnhancement.block_edge_cells(
                    model_orography_km, grid_km
                ),
                "zero_below_mmh": zero_below if index == 0 else 0.0,
            }
        )
    return specs
