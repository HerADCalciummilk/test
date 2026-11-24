# -*- coding: utf-8 -*-
"""按多个尺度依次做地形增强和降水订正。一次调用处理一个时次。"""
from __future__ import annotations

from typing import Optional

import meteva_base as meb
import numpy as np
import xarray as xr

from orographic_precipitation_downscaling.src.orographic_enhancement import (
    OrographicEnhancement,
)
from orographic_precipitation_downscaling.src.redistribute_orographic_enhancement import (
    RedistributeOrographicEnhancement,
)
from orographic_precipitation_downscaling.src.util_plugin import (
    _aggregate_factor,
    aggregate_orography,
    build_cascade_stages,
)
from orographic_precipitation_downscaling.src.utils._grid import _estimate_grid_spacing_meters
from orographic_precipitation_downscaling.utils.base_plugin import BasePlugin


def _on_grid(field: xr.DataArray, grid, units: str) -> xr.DataArray:
    """双线性插到目标网格，范围外为 NaN。"""
    moved = meb.interp_gg_linear(field, grid, outer_value=np.nan)
    moved.attrs["units"] = units
    return moved


class CascadeOrographicDownscaling(BasePlugin):
    """多尺度地形降水订正。每个尺度先算增强，再重分配降水。"""

    def process(
        self,
        precip: xr.DataArray,
        temperature: xr.DataArray,
        humidity: xr.DataArray,
        pressure: xr.DataArray,
        uwind: xr.DataArray,
        vwind: xr.DataArray,
        orography_model: xr.DataArray,
        orography_target: xr.DataArray,
        stages: str,
        zero_below: Optional[float] = None,
        wet_threshold: float = 0.1,
    ) -> xr.DataArray:
        for label, field in (
            ("相对湿度场", humidity),
            ("气压场", pressure),
            ("东西风场", uwind),
            ("南北风场", vwind),
        ):
            if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
                raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

        wet_threshold = float(wet_threshold)
        if wet_threshold < 0:
            raise ValueError(f"wet_threshold 须非负，收到 {wet_threshold}")

        # 降水格距必须在插值前从原始预报上量
        stage_specs = build_cascade_stages(
            stages,
            precip_spacing_km=_estimate_grid_spacing_meters(precip) / 1000.0,
            zero_below=zero_below,
        )
        target_km = float(stage_specs[-1]["to_km"])
        orogs: dict[float, xr.DataArray] = {
            float(stage_specs[0]["from_km"]): orography_model,
            target_km: orography_target,
        }
        for spec in stage_specs:
            grid_km = float(spec["to_km"])
            if grid_km in orogs:
                continue
            # 中间尺度的模式地形由目标地形按整数倍块平均得到
            orogs[grid_km] = aggregate_orography(
                orography_target, _aggregate_factor(grid_km, target_km)
            )

        # 每个地形尺度各算一次增强
        oe_api = OrographicEnhancement()
        enhancements: dict[float, xr.DataArray] = {}
        for level_km, orog in orogs.items():
            enhancement = oe_api.process(temperature, humidity, pressure, uwind, vwind, orog)
            if not str(enhancement.attrs.get("units") or "").strip():
                enhancement.attrs["units"] = "m s-1"
            enhancements[level_km] = enhancement

        precip_units = str(precip.attrs.get("units") or "mm h-1")
        field = precip
        for spec in stage_specs:
            model_km = float(spec["from_km"])
            grid_km = float(spec["to_km"])
            grid_orog = orogs[grid_km]
            grid = meb.get_grid_of_data(grid_orog)
            # 插件要求三张场已经在同一张目标网格上
            precip_on_grid = _on_grid(field, grid, precip_units)
            model_units = str(enhancements[model_km].attrs.get("units") or "m s-1")
            oe_model = _on_grid(enhancements[model_km], grid, model_units)
            oe_target = enhancements[grid_km]
            corrected, _adjustment = RedistributeOrographicEnhancement(
                wet_threshold_mmh=wet_threshold,
                zero_below_mmh=float(spec["zero_below_mmh"]),
                precip_spacing_km=float(spec["precip_spacing_km"]),
                model_orography_spacing_km=float(spec["model_orography_spacing_km"]),
            ).process(precip_on_grid, oe_target, oe_model)
            if not str(corrected.attrs.get("units") or "").strip():
                corrected.attrs["units"] = precip_units
            corrected.name = precip.name or "precipitation_rate"
            field = corrected
        return field
