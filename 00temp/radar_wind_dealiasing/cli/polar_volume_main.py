#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""极坐标体扫输入的转换与校验调度。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import xarray as xr


POLAR_VOLUME_DIMS = ("member", "level", "time", "dtime", "lat", "lon")
_SINGLE_CONTEXT_DIMS = POLAR_VOLUME_DIMS[:4]

__all__ = [
    "PolarVolumeInfo",
    "extract_polar_volume_sweep",
    "process",
    "pyart_radar_to_polar_volume",
    "read_polar_volume",
    "validate_polar_volume",
]


@dataclass(frozen=True)
class PolarVolumeInfo:
    """校验通过后的极坐标体扫布局信息。"""

    nrays: int
    ngates: int
    sweep_start_ray_index: np.ndarray
    sweep_end_ray_index: np.ndarray
    nyquist_velocity: np.ndarray
    fixed_angle: np.ndarray | None

    @property
    def nsweeps(self) -> int:
        """返回 sweep 数量。"""
        return int(self.sweep_start_ray_index.size)


def pyart_radar_to_polar_volume(
    radar,
    field_name: str,
    *,
    data_name: str | None = None,
    member_name: str = "radar",
    level_value: float = 0.0,
    time_value=None,
    dtime_value: int = 0,
    nyquist_velocity: float | Sequence[float] | None = None,
) -> xr.DataArray:
    """将 Py-ART Radar 中的一个字段转换为六维极坐标体扫。

    参数
    ----
    radar
        Py-ART ``Radar`` 对象。
    field_name : str
        需要转换的 ``radar.fields`` 字段名。
    data_name : str, optional
        输出 DataArray 名称；默认沿用 ``field_name``。
    member_name : str, optional
        六维容器的 member 坐标值。
    level_value : float, optional
        六维容器的 level 占位值。
    time_value : datetime-like, optional
        体扫时间；为空时尝试从 Radar 时间变量读取。
    dtime_value : int, optional
        六维容器的 dtime 坐标值。
    nyquist_velocity : float or sequence of float, optional
        显式 Nyquist 速度；为空时逐 sweep 从 Radar 读取。

    返回
    ----
    xr.DataArray
        满足 ``region_dealias`` 输入约定的六维极坐标体扫。
    """
    _validate_radar_structure(radar, field_name)
    field_meta = radar.fields[field_name]
    field_values = _masked_to_nan(
        field_meta["data"],
        field_meta.get("_FillValue"),
        field_meta.get("missing_value"),
    )
    nrays, ngates = field_values.shape

    starts = _radar_array(radar.sweep_start_ray_index, np.int32)
    ends = _radar_array(radar.sweep_end_ray_index, np.int32)
    fixed_angle = _radar_array(radar.fixed_angle, np.float32)
    azimuth = _radar_array(radar.azimuth, np.float64)
    elevation = _radar_array(radar.elevation, np.float64)
    ranges = _radar_array(radar.range, np.float64)
    nyquist = _resolve_radar_nyquist(
        radar,
        starts.size,
        nyquist_velocity,
    )

    sweep_index = np.empty(nrays, dtype=np.int32)
    for index, (start, end) in enumerate(zip(starts, ends)):
        sweep_index[int(start) : int(end) + 1] = index

    volume = xr.DataArray(
        field_values.reshape(1, 1, 1, 1, nrays, ngates),
        dims=POLAR_VOLUME_DIMS,
        coords={
            "member": [member_name],
            "level": [level_value],
            "time": [_resolve_radar_time(radar, time_value)],
            "dtime": [dtime_value],
            "lat": np.arange(nrays, dtype=np.int32),
            "lon": np.arange(ngates, dtype=np.int32),
            "azimuth": ("lat", azimuth),
            "elevation": ("lat", elevation),
            "sweep_index": ("lat", sweep_index),
            "range": ("lon", ranges),
        },
        name=data_name or field_name,
    )
    volume.coords["lat"].attrs.update(
        {"long_name": "ray index", "axis_semantics": "ray"}
    )
    volume.coords["lon"].attrs.update(
        {"long_name": "range gate index", "axis_semantics": "gate"}
    )
    _copy_coordinate_metadata(volume.coords["azimuth"], radar.azimuth)
    _copy_coordinate_metadata(volume.coords["elevation"], radar.elevation)
    _copy_coordinate_metadata(volume.coords["range"], radar.range)
    _attach_antenna_transition(volume, radar)

    volume.attrs.update(
        {
            "grid_axis_type": "radar_volume",
            "polar_volume_convention": "ray_gate_v1",
            "sweep_start_ray_index": starts.tolist(),
            "sweep_end_ray_index": ends.tolist(),
            "nyquist_velocity": nyquist.tolist(),
            "fixed_angle": fixed_angle.tolist(),
            "scan_type": str(getattr(radar, "scan_type", "")),
            "source_field": field_name,
        }
    )
    _copy_radar_location(volume.attrs, radar)
    _copy_field_metadata(volume.attrs, field_meta)
    validate_polar_volume(volume)
    return volume


def validate_polar_volume(
    volume: xr.DataArray,
    *,
    require_geolocation: bool = False,
) -> PolarVolumeInfo:
    """校验 DataArray 是否满足 region_dealias 极坐标体扫约定。

    参数
    ----
    volume : xr.DataArray
        待校验的六维极坐标体扫。
    require_geolocation : bool, optional
        是否同时要求方位角、共享距离轴和雷达站点经纬度。

    返回
    ----
    PolarVolumeInfo
        校验通过后的体扫布局信息。
    """
    if not isinstance(volume, xr.DataArray):
        raise TypeError("polar volume must be an xarray.DataArray")
    if tuple(volume.dims) != POLAR_VOLUME_DIMS:
        raise ValueError(
            "polar volume dimensions must be ordered as "
            f"{POLAR_VOLUME_DIMS}, got {tuple(volume.dims)}"
        )
    if not np.issubdtype(volume.dtype, np.number):
        raise TypeError("polar volume values must use a numeric dtype")

    for dim in _SINGLE_CONTEXT_DIMS:
        if int(volume.sizes[dim]) != 1:
            raise ValueError(f"polar volume dimension {dim!r} must have length 1")

    nrays = int(volume.sizes["lat"])
    ngates = int(volume.sizes["lon"])
    if nrays < 1 or ngates < 1:
        raise ValueError("polar volume must contain at least one ray and one gate")
    _validate_index_coordinate(volume, "lat", nrays)
    _validate_index_coordinate(volume, "lon", ngates)

    starts, ends = _parse_sweep_boundaries(volume.attrs, nrays)
    nsweeps = int(starts.size)
    nyquist = _parse_per_sweep_float(
        _first_attr(volume.attrs, "nyquist_velocity", "nyquist_vel"),
        nsweeps,
        "nyquist_velocity",
        required=True,
    )
    if np.any(~np.isfinite(nyquist)) or np.any(nyquist <= 0.0):
        raise ValueError("nyquist_velocity values must be finite and greater than zero")

    fixed_angle = _parse_per_sweep_float(
        volume.attrs.get("fixed_angle"),
        nsweeps,
        "fixed_angle",
        required=False,
    )
    _validate_optional_coordinate(volume, "azimuth", ("lat",), nrays)
    _validate_optional_coordinate(volume, "elevation", ("lat",), nrays)
    _validate_optional_coordinate(volume, "sweep_index", ("lat",), nrays)
    _validate_optional_coordinate(volume, "antenna_transition", ("lat",), nrays)
    _validate_optional_coordinate(volume, "range", ("lon",), ngates)

    if "sweep_index" in volume.coords:
        expected = np.empty(nrays, dtype=np.int32)
        for index, (start, end) in enumerate(zip(starts, ends)):
            expected[int(start) : int(end) + 1] = index
        if not np.array_equal(
            np.asarray(volume.coords["sweep_index"].values),
            expected,
        ):
            raise ValueError("sweep_index coordinate does not match sweep boundaries")

    if require_geolocation:
        for coord in ("azimuth", "range"):
            if coord not in volume.coords:
                raise ValueError(
                    f"{coord} coordinate is required for geolocation"
                )
        for attr in ("radar_lon", "radar_lat"):
            if attr not in volume.attrs:
                raise ValueError(f"{attr} attribute is required for geolocation")
            if not np.isfinite(float(volume.attrs[attr])):
                raise ValueError(f"{attr} attribute must be finite")

    return PolarVolumeInfo(
        nrays=nrays,
        ngates=ngates,
        sweep_start_ray_index=starts,
        sweep_end_ray_index=ends,
        nyquist_velocity=nyquist,
        fixed_angle=fixed_angle,
    )


def extract_polar_volume_sweep(
    volume: xr.DataArray,
    sweep_index: int = 0,
) -> xr.DataArray:
    """从完整体扫中截取单个扫描层，仍保持六维极坐标约定。

    截取后 ``sweep_start_ray_index/sweep_end_ray_index`` 重置为单层边界，
    ``nyquist_velocity`` / ``fixed_angle`` 仅保留对应扫描层的值。
    """
    info = validate_polar_volume(volume)
    if sweep_index < 0 or sweep_index >= info.nsweeps:
        raise ValueError(
            f"sweep_index must be in [0, {info.nsweeps - 1}], got {sweep_index}"
        )

    start = int(info.sweep_start_ray_index[sweep_index])
    end = int(info.sweep_end_ray_index[sweep_index])
    ray_slice = slice(start, end + 1)
    nrays = end - start + 1

    extracted = volume.isel(lat=ray_slice).copy(deep=True)
    extracted = extracted.assign_coords(lat=np.arange(nrays, dtype=np.int32))
    if "sweep_index" in extracted.coords:
        extracted = extracted.assign_coords(
            sweep_index=("lat", np.zeros(nrays, dtype=np.int32))
        )

    extracted.attrs["sweep_start_ray_index"] = [0]
    extracted.attrs["sweep_end_ray_index"] = [nrays - 1]
    extracted.attrs["nyquist_velocity"] = [
        float(info.nyquist_velocity[sweep_index])
    ]
    if info.fixed_angle is not None:
        extracted.attrs["fixed_angle"] = [float(info.fixed_angle[sweep_index])]

    validate_polar_volume(extracted)
    return extracted


def read_polar_volume(
    path: str | Path,
    *,
    value_name: str | None = None,
) -> xr.DataArray:
    """从 NetCDF 读取一个极坐标体扫字段并保留辅助坐标。"""
    with xr.open_dataset(path) as dataset:
        if value_name is not None:
            if value_name not in dataset.data_vars:
                raise ValueError(
                    f"value_name={value_name!r} was not found in {path}"
                )
            volume = dataset[value_name].load()
        else:
            candidates = [
                name
                for name, variable in dataset.data_vars.items()
                if set(POLAR_VOLUME_DIMS).issubset(variable.dims)
            ]
            if len(candidates) != 1:
                raise ValueError(
                    "NetCDF input must contain exactly one six-dimensional "
                    "field when value_name is not specified"
                )
            volume = dataset[candidates[0]].load()
    return volume.transpose(*POLAR_VOLUME_DIMS)


def process(
    radar_path: str,
    field_name: str,
    *,
    output_path: str | None = None,
    data_name: str | None = None,
    member_name: str = "radar",
    level_value: float = 0.0,
    time_value=None,
    dtime_value: int = 0,
    nyquist_velocity: float | Sequence[float] | None = None,
    require_geolocation: bool = False,
) -> xr.DataArray:
    """读取 Py-ART 雷达文件，转换并校验指定字段。

    参数
    ----
    radar_path : str
        Py-ART 支持的雷达文件路径。
    field_name : str
        需要转换的 Radar 字段名。
    output_path : str, optional
        输出 NetCDF 路径；为空时仅返回内存结果。
    data_name, member_name, level_value, time_value, dtime_value
        输出六维 DataArray 的名称和容器坐标。
    nyquist_velocity : float or sequence of float, optional
        显式 Nyquist 速度；为空时从 Radar 逐 sweep 读取。
    require_geolocation : bool, optional
        是否要求输出具备地理后处理所需元数据。

    返回
    ----
    xr.DataArray
        转换并校验通过的极坐标体扫。
    """
    try:
        import pyart
    except ImportError as exc:
        raise ImportError("Py-ART is required to read radar_path") from exc

    from radar_wind_dealiasing.cli import _write_griddata_to_nc

    radar = pyart.io.read(radar_path)
    volume = pyart_radar_to_polar_volume(
        radar,
        field_name,
        data_name=data_name,
        member_name=member_name,
        level_value=level_value,
        time_value=time_value,
        dtime_value=dtime_value,
        nyquist_velocity=nyquist_velocity,
    )
    validate_polar_volume(
        volume,
        require_geolocation=require_geolocation,
    )
    if output_path is not None:
        _write_griddata_to_nc(volume, output_path)
    return volume


def _validate_radar_structure(radar, field_name):
    if not hasattr(radar, "fields") or field_name not in radar.fields:
        raise ValueError(f"Radar field {field_name!r} was not found")
    values = np.asanyarray(radar.fields[field_name].get("data"))
    expected_shape = (int(radar.nrays), int(radar.ngates))
    if values.shape != expected_shape:
        raise ValueError(
            f"Radar field {field_name!r} shape must be {expected_shape}, "
            f"got {values.shape}"
        )


def _masked_to_nan(data, fill_value=None, missing_value=None):
    if np.ma.isMaskedArray(data):
        values = np.asarray(data.data, dtype=np.float32).copy()
        values[np.ma.getmaskarray(data)] = np.nan
    else:
        values = np.asarray(data, dtype=np.float32).copy()

    for candidate in (fill_value, missing_value):
        try:
            candidate = float(candidate)
        except (TypeError, ValueError):
            continue
        if np.isfinite(candidate):
            values[np.isclose(values, candidate, rtol=0.0, atol=0.0)] = np.nan
    return values


def _radar_array(metadata, dtype):
    return np.asarray(metadata["data"], dtype=dtype).reshape(-1)


def _resolve_radar_nyquist(radar, nsweeps, explicit):
    if explicit is not None:
        return _parse_per_sweep_float(
            explicit,
            nsweeps,
            "nyquist_velocity",
            required=True,
        )

    values = []
    for sweep in range(nsweeps):
        try:
            value = radar.get_nyquist_vel(sweep, check_uniform=False)
        except Exception as exc:
            raise ValueError(
                f"cannot determine Nyquist velocity for sweep {sweep}"
            ) from exc
        values.append(float(value))
    return np.asarray(values, dtype=np.float32)


def _resolve_radar_time(radar, explicit):
    if explicit is not None:
        return np.datetime64(explicit)
    try:
        from netCDF4 import num2date

        value = np.asarray(radar.time["data"]).reshape(-1)[0]
        units = radar.time["units"]
        calendar = radar.time.get("calendar", "standard")
        timestamp = num2date(
            value,
            units,
            calendar=calendar,
            only_use_cftime_datetimes=False,
        )
        if getattr(timestamp, "tzinfo", None) is not None:
            timestamp = timestamp.replace(tzinfo=None)
        return np.datetime64(timestamp)
    except Exception:
        return np.datetime64("1970-01-01T00:00:00")


def _copy_coordinate_metadata(target, source):
    for key in ("units", "long_name", "standard_name"):
        if key in source:
            target.attrs[key] = source[key]


def _attach_antenna_transition(volume: xr.DataArray, radar) -> None:
    """若 Radar 提供 antenna_transition，则写入 ray 维辅助坐标。"""
    transition = getattr(radar, "antenna_transition", None)
    if transition is None:
        return
    if not isinstance(transition, dict) or "data" not in transition:
        raise TypeError("radar.antenna_transition must be None or a dict with 'data'")
    values = np.asarray(transition["data"]).reshape(-1)
    if values.size != int(volume.sizes["lat"]):
        raise ValueError(
            "radar.antenna_transition length must equal the number of rays"
        )
    volume.coords["antenna_transition"] = (
        "lat",
        values.astype(np.int8, copy=False),
    )
    volume.coords["antenna_transition"].attrs.update(
        {
            "long_name": "antenna transition flag",
            "comment": (
                "1 = ray collected while antenna was in transition, "
                "0 = otherwise"
            ),
        }
    )
    _copy_coordinate_metadata(volume.coords["antenna_transition"], transition)


def _copy_radar_location(attrs, radar):
    for attr_name, radar_name in (
        ("radar_lon", "longitude"),
        ("radar_lat", "latitude"),
        ("radar_altitude", "altitude"),
    ):
        metadata = getattr(radar, radar_name, None)
        if metadata is None:
            continue
        values = np.asarray(metadata.get("data", []), dtype=np.float64).reshape(-1)
        if values.size and np.isfinite(values[0]):
            attrs[attr_name] = float(values[0])


def _copy_field_metadata(attrs, field_meta):
    for key in (
        "units",
        "long_name",
        "standard_name",
        "_FillValue",
        "missing_value",
    ):
        if key not in field_meta:
            continue
        value = field_meta[key]
        attrs[key] = value.item() if isinstance(value, np.generic) else value


def _validate_index_coordinate(volume, name, size):
    values = np.asarray(volume.coords[name].values)
    expected = np.arange(size)
    if values.ndim != 1 or not np.array_equal(values, expected):
        raise ValueError(f"{name} coordinate must contain consecutive indices from 0")


def _parse_sweep_boundaries(attrs, nrays):
    starts_value = attrs.get("sweep_start_ray_index")
    ends_value = attrs.get("sweep_end_ray_index")
    if starts_value is None and ends_value is None:
        return (
            np.array([0], dtype=np.int32),
            np.array([nrays - 1], dtype=np.int32),
        )
    if starts_value is None or ends_value is None:
        raise ValueError(
            "sweep_start_ray_index and sweep_end_ray_index must be provided together"
        )

    starts = _parse_integer_vector(starts_value, "sweep_start_ray_index")
    ends = _parse_integer_vector(ends_value, "sweep_end_ray_index")
    if starts.size == 0 or starts.size != ends.size:
        raise ValueError("sweep boundary arrays must have the same non-zero length")
    if starts[0] != 0 or ends[-1] != nrays - 1:
        raise ValueError("sweep boundaries must cover all rays")
    if np.any(starts < 0) or np.any(ends < starts) or np.any(ends >= nrays):
        raise ValueError("sweep boundaries contain an invalid ray range")
    if starts.size > 1 and np.any(starts[1:] != ends[:-1] + 1):
        raise ValueError("sweep ray ranges must be contiguous and non-overlapping")
    return starts, ends


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
        raise ValueError(f"{name} must be a scalar or contain one value per sweep")
    return values


def _first_attr(attrs: dict[str, Any], *names):
    for name in names:
        if name in attrs:
            return attrs[name]
    return None


def _validate_optional_coordinate(volume, name, dims, size):
    if name not in volume.coords:
        return
    coordinate = volume.coords[name]
    if coordinate.dims != dims or coordinate.size != size:
        raise ValueError(
            f"{name} coordinate must have dimensions {dims} and length {size}"
        )


if __name__ == "__main__":
    import sys

    import pyart

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from radar_wind_dealiasing.cli.polar_volume_main import (
        pyart_radar_to_polar_volume,
        validate_polar_volume,
    )

    # 与 notebook 对齐：固定 CfRadial → 仅写出单个扫描层样例（控制仓库体积）
    data_dir = (
        Path(__file__).resolve().parents[1]
        / "test_data"
        / "region_dealias"
    )
    cli_input_dir = data_dir / "cli_input"
    cli_input_dir.mkdir(parents=True, exist_ok=True)

    mdv_file = data_dir / "095636.mdv"
    cfradial_file = cli_input_dir / "radar_fixed.cfradial.nc"
    sweep_index = 0
    velocity_file = cli_input_dir / f"velocity_sweep{sweep_index}.nc"

    if not cfradial_file.exists():
        radar_mdv = pyart.io.read_mdv(str(mdv_file))
        pyart.io.write_cfradial(str(cfradial_file), radar_mdv)

    radar = pyart.io.read_cfradial(str(cfradial_file))
    radar_sweep = radar.extract_sweeps([sweep_index])
    volume = pyart_radar_to_polar_volume(radar_sweep, "velocity")
    validate_polar_volume(volume, require_geolocation=True)

    # 落盘方式与 notebook 的 save_griddata 保持一致
    var_name = volume.name or "velocity"
    volume.to_dataset(name=var_name).to_netcdf(
        velocity_file,
        encoding={
            var_name: {"dtype": "float32", "zlib": True, "complevel": 1},
        },
    )
