#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""核心算法使用的极坐标体扫布局解析。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xarray as xr


@dataclass(frozen=True)
class PolarVolumeLayout:
    """完整体扫的 sweep 切片和逐 sweep 元数据。"""

    sweep_slices: tuple[slice, ...]
    nyquist_velocity: np.ndarray
    fixed_angle: np.ndarray

    @property
    def nsweeps(self) -> int:
        """返回 sweep 数量。"""
        return len(self.sweep_slices)


def _replace_polar_volume_values(
    template: xr.DataArray,
    data: np.ndarray,
) -> xr.DataArray:
    """替换体扫数值，同时保留 sweep 属性和辅助坐标。"""
    values = np.asarray(data, dtype=np.float32)
    if values.shape != template.shape:
        raise ValueError(
            f"data shape must match polar volume shape: "
            f"{values.shape} vs {template.shape}"
        )
    return template.copy(data=values)


def parse_polar_volume_layout(
    velocity: xr.DataArray,
    nyquist_velocity=None,
) -> PolarVolumeLayout:
    """解析核心退模糊所需的体扫边界和 Nyquist 速度。"""
    for dim in ("member", "level", "time", "dtime"):
        if int(velocity.sizes[dim]) != 1:
            raise ValueError(
                f"polar volume dimension {dim!r} must have length 1"
            )

    nrays = int(velocity.sizes["lat"])
    if nrays < 1:
        raise ValueError("polar volume must contain at least one ray")

    starts_value = velocity.attrs.get("sweep_start_ray_index")
    ends_value = velocity.attrs.get("sweep_end_ray_index")
    if starts_value is None and ends_value is None:
        starts = np.array([0], dtype=np.int32)
        ends = np.array([nrays - 1], dtype=np.int32)
    elif starts_value is None or ends_value is None:
        raise ValueError(
            "sweep_start_ray_index and sweep_end_ray_index "
            "must be provided together"
        )
    else:
        starts = _parse_integer_vector(
            starts_value,
            "sweep_start_ray_index",
        )
        ends = _parse_integer_vector(
            ends_value,
            "sweep_end_ray_index",
        )

    if starts.size == 0 or starts.size != ends.size:
        raise ValueError(
            "sweep boundary arrays must have the same non-zero length"
        )
    if starts[0] != 0 or ends[-1] != nrays - 1:
        raise ValueError("sweep boundaries must cover all rays")
    if np.any(starts < 0) or np.any(ends < starts) or np.any(ends >= nrays):
        raise ValueError("sweep boundaries contain an invalid ray range")
    if starts.size > 1 and np.any(starts[1:] != ends[:-1] + 1):
        raise ValueError(
            "sweep ray ranges must be contiguous and non-overlapping"
        )

    nsweeps = int(starts.size)
    nyquist = _parse_per_sweep_float(
        nyquist_velocity
        if nyquist_velocity is not None
        else _first_attr(velocity.attrs, "nyquist_velocity", "nyquist_vel"),
        nsweeps,
        "nyquist_velocity",
        required=True,
    )
    if np.any(~np.isfinite(nyquist)) or np.any(nyquist <= 0.0):
        raise ValueError(
            "nyquist_velocity values must be finite and greater than zero"
        )

    fixed_angle = _parse_per_sweep_float(
        velocity.attrs.get("fixed_angle"),
        nsweeps,
        "fixed_angle",
        required=False,
    )
    if fixed_angle is None:
        fixed_angle = np.arange(nsweeps, dtype=np.float32)

    return PolarVolumeLayout(
        sweep_slices=tuple(
            slice(int(start), int(end) + 1)
            for start, end in zip(starts, ends)
        ),
        nyquist_velocity=nyquist,
        fixed_angle=fixed_angle,
    )


def _parse_integer_vector(value, name):
    raw = np.asarray(value)
    if raw.ndim == 0:
        raw = raw.reshape(1)
    if raw.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional sequence")
    try:
        numeric = raw.astype(np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain integers") from exc
    if np.any(~np.isfinite(numeric)) or np.any(numeric != np.floor(numeric)):
        raise ValueError(f"{name} must contain integers")
    return numeric.astype(np.int32)


def _parse_per_sweep_float(value, size, name, *, required):
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    try:
        values = np.asarray(value, dtype=np.float32).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values") from exc
    if values.size == 1:
        return np.full(size, float(values[0]), dtype=np.float32)
    if values.size != size:
        raise ValueError(
            f"{name} must be a scalar or contain one value per sweep"
        )
    return values


def _first_attr(attrs, *names):
    for name in names:
        if name in attrs:
            return attrs[name]
    return None
