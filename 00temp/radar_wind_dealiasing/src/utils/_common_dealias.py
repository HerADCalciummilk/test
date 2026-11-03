#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""区域退模糊共用辅助函数。"""

from __future__ import annotations

import meteva_base as meb
import numpy as np
import xarray as xr

from radar_wind_dealiasing.src.grid_gate_filter import GridGateFilter


def _normalize_optional_grid(
    grid_data: xr.DataArray | None,
    velocity_grid: xr.DataArray,
    field_name: str,
) -> xr.DataArray | None:
    """将可选辅助场规范为与速度场对齐的网格数据。"""
    if grid_data is None:
        return None

    normalized = meb.checkout_griddata(
        grid_data,
        is_single=False,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    # 辅助场虽然不直接参与展开求解，但必须与速度场严格共网格。
    if not meb.checkout_griddata_same_coords(
        [velocity_grid, normalized], is_time_match=True
    ):
        raise ValueError(f"velocity and {field_name} grid coordinates must be same")
    return normalized


def _as_ray_gate_excluded(gate_excluded) -> np.ndarray:
    """将过滤器掩码规范为二维 (ray, gate) 布尔数组。"""
    mask = np.asarray(gate_excluded, dtype=bool).copy()
    if mask.ndim == 6:
        mask = mask[0, 0, 0, 0]
    if mask.ndim != 2:
        raise ValueError("gatefilter mask must resolve to a 2D ray/gate array")
    return mask


def _parse_gatefilter(
    gatefilter,
    velocity,
    refl=None,
    ncp=None,
    rhv=None,
    min_ncp=0.5,
    min_rhv=None,
    min_refl=-20.0,
    max_refl=100.0,
):
    """将 gatefilter 参数解析为 GridGateFilter。"""
    if gatefilter is None:
        return _moment_based_gatefilter(
            velocity,
            refl=refl,
            ncp=ncp,
            rhv=rhv,
            min_ncp=min_ncp,
            min_rhv=min_rhv,
            min_refl=min_refl,
            max_refl=max_refl,
        )
    if gatefilter is False:
        return GridGateFilter(velocity)
    if isinstance(gatefilter, GridGateFilter):
        return gatefilter.copy()
    raise TypeError("gatefilter must be None, False, or GridGateFilter")


def _moment_based_gatefilter(
    velocity: xr.DataArray,
    refl: xr.DataArray | None = None,
    ncp: xr.DataArray | None = None,
    rhv: xr.DataArray | None = None,
    min_ncp: float | None = 0.5,
    min_rhv: float | None = None,
    min_refl: float | None = -20.0,
    max_refl: float | None = 100.0,
):
    """按 Py-ART 主要矩量规则构建 GridGateFilter。

    约定由调用方（如 ``_normalize_optional_grid``）完成网格规范化；
    此处只做坐标一致性检查与门控规则。
    ``exclude_*`` 内部仍会经 ``GridGateFilter._get_fdata`` 再校验一次。
    """
    gatefilter = GridGateFilter(velocity)
    # 与 Py-ART moment_based_gate_filter 一致：优先排除天线过渡射线。
    gatefilter.exclude_transition()

    if (min_ncp is not None) and (ncp is not None):
        if not meb.checkout_griddata_same_coords([velocity, ncp]):
            raise ValueError("velocity and ncp grid coordinates must be same")
        gatefilter.exclude_below(ncp, min_ncp)
        gatefilter.exclude_masked(ncp)
        gatefilter.exclude_invalid(ncp)

    if (min_rhv is not None) and (rhv is not None):
        if not meb.checkout_griddata_same_coords([velocity, rhv]):
            raise ValueError("velocity and rhv grid coordinates must be same")
        gatefilter.exclude_below(rhv, min_rhv)
        gatefilter.exclude_masked(rhv)
        gatefilter.exclude_invalid(rhv)

    if refl is not None and (min_refl is not None or max_refl is not None):
        if not meb.checkout_griddata_same_coords([velocity, refl]):
            raise ValueError("velocity and refl grid coordinates must be same")
        gatefilter.exclude_outside(refl, min_refl, max_refl)
        gatefilter.exclude_masked(refl)
        gatefilter.exclude_invalid(refl)

    return gatefilter


def _parse_rays_wrap_around(rays_wrap_around, velocity):
    """解析首尾射线是否应相连。

    未显式指定时仅根据 ``scan_type == "ppi"`` 判断，与 Py-ART 一致。
    """
    if rays_wrap_around is not None:
        return bool(rays_wrap_around)

    scan_type = str(velocity.attrs.get("scan_type", "")).strip().lower()
    return scan_type == "ppi"


def _set_limits(data, nyquist_vel, attrs):
    """按退模糊结果写入输出的 valid_min / valid_max。"""
    max_abs_vel = np.ma.max(np.ma.abs(data))
    if max_abs_vel is np.ma.masked:
        return

    max_nyq_vel = np.ma.max(nyquist_vel)
    max_nyq_int = 2.0 * max_nyq_vel
    added_intervals = np.ceil((max_abs_vel - max_nyq_vel) / max_nyq_int)
    max_valid_velocity = max_nyq_vel + added_intervals * max_nyq_int
    attrs["valid_min"] = float(-max_valid_velocity)
    attrs["valid_max"] = float(max_valid_velocity)
