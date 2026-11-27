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
from orographic_precipitation_downscaling.src.utils._grid import _estimate_grid_spacing_meters
from orographic_precipitation_downscaling.utils.base_plugin import BasePlugin


def _on_grid(field: xr.DataArray, grid, units: str) -> xr.DataArray:
    """双线性插到目标网格，范围外为 NaN。"""
    moved = meb.interp_gg_linear(field, grid, outer_value=np.nan)
    moved.attrs["units"] = units
    return moved


class CascadeOrographicDownscaling(BasePlugin):
    """多尺度地形降水订正。每个尺度先算增强，再重分配降水。"""

    @staticmethod
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

    @staticmethod
    def _aggregate_factor(level_km: float, target_km: float) -> int:
        """目标地形聚合成该档网格时的整数倍数。"""
        ratio = float(level_km) / float(target_km)
        factor = int(round(ratio))
        if factor < 2 or abs(ratio - factor) > 1e-3:
            raise ValueError(
                f"分辨率 {level_km:g} km 不是目标 {target_km:g} km 的整数倍（≥2），无法聚合地形"
            )
        return factor

    @staticmethod
    def aggregate_orography(orog_target: xr.DataArray, factor: int) -> xr.DataArray:
        """把目标地形按 factor×factor 块平均到更粗的网格。"""
        out = orog_target.coarsen(lat=factor, lon=factor, boundary="trim").mean()
        out.attrs = dict(orog_target.attrs)
        out.attrs["units"] = orog_target.attrs.get("units") or "m"
        out.name = orog_target.name or "orography"
        return out

    @classmethod
    def build_cascade_stages(
        cls,
        stages: str,
        *,
        precip_spacing_km: float,
        zero_below: Optional[float] = None,
    ) -> list[dict]:
        """把尺度列表展开成每一次订正的设置。

        每次订正记下自己的降水格距和模式地形格距。
        ``zero_below`` 只赋给最粗一次。
        """
        levels = cls._parse_level_km(stages)
        if zero_below is None:
            zero_below = 0.0
        zero_below = float(zero_below)
        if zero_below < 0:
            raise ValueError(f"zero_below 须非负，收到 {zero_below}")
        if float(precip_spacing_km) <= 0:
            raise ValueError(f"precip_spacing_km 须为正，收到 {precip_spacing_km}")

        target_km = levels[-1]
        for level_km in levels[1:-1]:
            cls._aggregate_factor(level_km, target_km)

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
        stage_specs = self.build_cascade_stages(
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
            orogs[grid_km] = self.aggregate_orography(
                orography_target, self._aggregate_factor(grid_km, target_km)
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
