# -*- coding: utf-8 -*-
"""质控后极坐标场 → meteva 六维经纬网格。

供 ``PolarRadarQCPlugin`` 内建网格化使用；CLI ``polar_qc`` 再导出同名函数。
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd
import meteva_base as meb
import xarray as xr
from radar_qpe_retrieval.src.grid_2d import grid_2d

# Py-ART 场名 → (meteva 变量名, 单位)
FIELD_META = {
    "reflectivity": ("reflectivity", "dBZ"),
    "specific_differential_phase": ("specific_differential_phase", "deg/km"),
    "cross_correlation_ratio": ("cross_correlation_ratio", "1"),
    "differential_reflectivity": ("differential_reflectivity", "dB"),
    "specific_attenuation": ("specific_attenuation", "dB/km"),
    "corrected_reflectivity": ("corrected_reflectivity", "dBZ"),
    "path_integrated_attenuation": ("path_integrated_attenuation", "dB"),
}

# 标准格式产品名 → (meteva 变量名, 单位)
STANDARD_PRODUCT_META = {
    "REF": ("reflectivity", "dBZ"),
    "TREF": ("total_reflectivity", "dBZ"),
    "KDP": ("specific_differential_phase", "deg/km"),
    "ZDR": ("differential_reflectivity", "dB"),
    "RHO": ("cross_correlation_ratio", "1"),
    "PHI": ("differential_phase", "deg"),
    "VEL": ("velocity", "m/s"),
    "SW": ("spectrum_width", "m/s"),
}

DEFAULT_STANDARD_GRID_FIELDS = ("REF",)

# QPE 常用输出场（插件默认网格化这些）
DEFAULT_QPE_GRID_FIELDS = (
    "reflectivity",
    "specific_differential_phase",
    "specific_attenuation",
)


def _cinrad_frequency_hz(cinrad_file) -> float | None:
    wl_cm = getattr(cinrad_file, "wavelength", None)
    if wl_cm is None:
        return None
    wl_cm = float(wl_cm)
    if not np.isfinite(wl_cm) or wl_cm <= 0:
        return None
    return 3e8 / (wl_cm * 0.01)


def _site_code_of(radar_file) -> str:
    for key in ("code", "site_code"):
        val = getattr(radar_file, key, None)
        if val:
            return str(val)
    return "RADAR"


def _site_name_of(radar_file) -> str | None:
    for key in ("name", "site_name"):
        val = getattr(radar_file, key, None)
        if val:
            return str(val)
    return None


def _apply_cinrad_grid_attrs(gdata: meb.grid_data, cinrad_file) -> None:
    gdata.attrs["site_code"] = _site_code_of(cinrad_file)
    gdata.attrs["scan_time"] = str(pd.to_datetime(cinrad_file.scantime))
    freq_hz = _cinrad_frequency_hz(cinrad_file)
    if freq_hz is not None:
        gdata.attrs["frequency"] = float(freq_hz)
        gdata.attrs["frequency_units"] = "Hz"
    site_name = _site_name_of(cinrad_file)
    if site_name:
        gdata.attrs["site_name"] = site_name
    lon = getattr(cinrad_file, "stationlon", None)
    lat = getattr(cinrad_file, "stationlat", None)
    if lon is not None:
        gdata.attrs["site_longitude"] = float(lon)
    if lat is not None:
        gdata.attrs["site_latitude"] = float(lat)


def _radar_site_member(radar) -> str:
    meta = getattr(radar, "metadata", None) or {}
    for key in ("instrument_name", "radar_name", "site_name"):
        val = meta.get(key)
        if val:
            return str(val)
    return "RADAR"


def _radar_scan_time(radar) -> pd.Timestamp:
    units = radar.time.get("units", "seconds since 1970-01-01T00:00:00Z")
    t0 = np.asarray(radar.time["data"], dtype=np.float64)
    try:
        base = pd.Timestamp(str(units).split("since", 1)[1].strip())
    except Exception:
        base = pd.Timestamp("1970-01-01T00:00:00Z")
    return base + pd.to_timedelta(float(t0[0]), unit="s")


def _radar_level_coords(radar) -> dict:
    elev = np.asarray(radar.fixed_angle["data"], dtype=np.float64)
    alt = float(np.asarray(radar.altitude["data"]).ravel()[0])
    range_m = float(np.nanmax(radar.range["data"]))
    height_m = alt + range_m * np.sin(np.deg2rad(elev))
    return {
        "tilt_indices": list(range(int(radar.nsweeps))),
        "level_list": [float(v) for v in elev],
        "elevation_deg": elev,
        "height_m": height_m.astype(np.float64),
        "height_reference": "site_alt + max_range*sin(elevation)",
        "range_m_used": range_m,
        "site_alt_m": alt,
    }


def _apply_radar_attrs(gdata: meb.grid_data, radar, cinrad_file=None) -> None:
    gdata.attrs["site_code"] = _radar_site_member(radar)
    gdata.attrs["scan_time"] = str(_radar_scan_time(radar))
    gdata.attrs["site_longitude"] = float(np.asarray(radar.longitude["data"]).ravel()[0])
    gdata.attrs["site_latitude"] = float(np.asarray(radar.latitude["data"]).ravel()[0])
    gdata.attrs["site_alt_m"] = float(np.asarray(radar.altitude["data"]).ravel()[0])
    if cinrad_file is not None:
        _apply_cinrad_grid_attrs(gdata, cinrad_file)


def _check_same_horiz_coordinates(grd_list: list[xr.DataArray]) -> bool:
    if not grd_list:
        return False
    ref = grd_list[0]
    for grd in grd_list[1:]:
        if not (
            (grd.member.values == ref.member.values).all()
            and np.allclose(grd.lat.values, ref.lat.values, atol=0.001)
            and np.allclose(grd.lon.values, ref.lon.values, atol=0.001)
        ):
            return False
    return True


def _attach_sweep_level_metadata(
    grid_data: xr.DataArray,
    level_coords: dict,
) -> xr.DataArray:
    normalized = meb.checkout_griddata(grid_data, is_single=False)
    elevation_deg = np.asarray(level_coords["elevation_deg"], dtype=np.float64).ravel()
    height_m = np.asarray(level_coords["height_m"], dtype=np.float64).ravel()
    if elevation_deg.size != int(normalized.sizes["level"]):
        raise ValueError(
            "elevation_deg length must match grid level size: "
            f"{elevation_deg.size} vs {int(normalized.sizes['level'])}"
        )
    if height_m.size != elevation_deg.size:
        raise ValueError("height_m must have the same length as elevation_deg")

    out = normalized.copy()
    out.attrs["level_coordinate"] = "elevation_deg"
    out.attrs["elevation_deg"] = [float(v) for v in elevation_deg]
    out.attrs["height_m"] = [float(v) for v in height_m]
    if "height_reference" in level_coords:
        out.attrs["height_reference"] = str(level_coords["height_reference"])
    if "range_m_used" in level_coords:
        out.attrs["range_m_used"] = float(level_coords["range_m_used"])
    if "site_alt_m" in level_coords:
        out.attrs["site_alt_m"] = float(level_coords["site_alt_m"])

    if "level" in out.coords:
        out.coords["level"].attrs["units"] = "degrees"
        out.coords["level"].attrs["standard_name"] = "elevation_angle"
        out.coords["level"].attrs["long_name"] = "radar fixed angle"
    return out


def _stack_gridded_sweeps(
    sweep_grids: list[xr.DataArray],
    level_coords: dict,
) -> xr.DataArray:
    if not sweep_grids:
        raise ValueError("sweep_grids must not be empty")
    if not _check_same_horiz_coordinates(sweep_grids):
        raise ValueError(
            "sweep_grids must share the same member/lat/lon coordinates "
            "(level may differ per sweep before stacking)"
        )

    nlevel = len(sweep_grids)
    if nlevel != len(level_coords["level_list"]):
        raise ValueError("sweep_grids length must match level_list length")

    parts = []
    for grid in sweep_grids:
        part = meb.checkout_griddata(grid, is_single=False)
        if int(part.sizes["level"]) != 1:
            raise ValueError("each sweep grid must have level dimension size 1")
        parts.append(part.values.astype(np.float32, copy=False))

    stacked_values = np.concatenate(parts, axis=1)
    template = meb.checkout_griddata(sweep_grids[0], is_single=False)
    base_grid = meb.get_grid_of_data(template)
    dtime_list = getattr(base_grid, "dtime_list", None)
    if dtime_list is None:
        dtime_list = list(base_grid.dtimes)
    member_list = getattr(base_grid, "member_list", None)
    if member_list is None:
        member_list = list(base_grid.members)

    volume_grid = meb.grid(
        base_grid.glon,
        base_grid.glat,
        gtime=base_grid.gtime,
        dtime_list=dtime_list,
        level_list=list(level_coords["level_list"]),
        member_list=member_list,
        level_type_attr="elevation",
    )
    volume = meb.grid_data(volume_grid, data=stacked_values)
    return _attach_sweep_level_metadata(volume, level_coords)


def _cinrad_layer_to_meteva(
    data_2d: np.ndarray,
    lon_1d: np.ndarray,
    lat_1d: np.ndarray,
    *,
    field_name: str,
    cinrad_file,
    level: float,
    units: str,
    member: str | None = None,
    time: pd.Timestamp | None = None,
) -> meb.grid_data:
    if len(lon_1d) < 2 or len(lat_1d) < 2:
        raise ValueError("grid_2d 输出经纬度维度过小")
    dlon = float(lon_1d[1] - lon_1d[0])
    dlat = float(lat_1d[1] - lat_1d[0])
    if time is None:
        time = pd.to_datetime(cinrad_file.scantime)
    member = member or _site_code_of(cinrad_file)

    grid = meb.grid(
        [float(lon_1d.min()), float(lon_1d.max()), dlon],
        [float(lat_1d.min()), float(lat_1d.max()), dlat],
        gtime=time,
        dtime_list=[0],
        level_list=[float(level)],
        member_list=[member],
    )
    gdata = meb.grid_data(grid, np.asarray(data_2d, dtype=np.float32))
    gdata.name = field_name
    gdata.attrs["units"] = units
    gdata.attrs["var_name"] = field_name
    gdata.attrs["data_name"] = member
    _apply_cinrad_grid_attrs(gdata, cinrad_file)
    return gdata


def _standard_level_coords(radar_file, dtype: str, drange) -> dict:
    tilts = radar_file.available_tilt(dtype)
    if not tilts:
        raise ValueError(f"no tilt available for product {dtype!r}")
    elev = np.asarray(
        [float(radar_file.get_elevation(t)) for t in tilts], dtype=np.float64
    )
    alt = float(getattr(radar_file, "radarheight", 0.0) or 0.0)
    range_km = radar_file.get_range_axis(tilts[0], dtype=dtype, drange=drange)
    range_m = float(np.nanmax(range_km)) * 1000.0 if range_km.size else 0.0
    height_m = alt + range_m * np.sin(np.deg2rad(elev))
    return {
        "tilt_indices": list(tilts),
        "level_list": [float(v) for v in elev],
        "elevation_deg": elev,
        "height_m": height_m.astype(np.float64),
        "height_reference": "site_alt + max_range*sin(elevation)",
        "range_m_used": range_m,
        "site_alt_m": alt,
    }


def standard_field_to_meteva_volume(
    radar_file,
    dtype: str = "REF",
    *,
    resolution: Sequence[int] = (1000, 1000),
    drange=None,
):
    """标准格式体积单产品 → 全仰角 meteva 经纬体扫网格（无 cinrad）。"""
    product = str(dtype).upper()
    tilts = radar_file.available_tilt(product)
    if not tilts:
        raise KeyError(f"radar has no product {product!r}")

    out_name, units = STANDARD_PRODUCT_META.get(product, (product, "1"))
    level_coords = _standard_level_coords(radar_file, product, drange)
    member = _site_code_of(radar_file)
    scan_time = pd.to_datetime(radar_file.scantime)

    x_out = y_out = None
    sweep_grids = []
    for tilt, elev in zip(level_coords["tilt_indices"], level_coords["level_list"]):
        data = np.asarray(
            radar_file.get_array(
                tilt=tilt,
                drange=drange,
                dtype=product,
                fill_value=np.nan,
                out_dtype=np.float32,
            ),
            dtype=np.float32,
        )
        lon, lat = radar_file.get_gate_lon_lat(tilt, dtype=product, drange=drange)
        gridded, x_out, y_out = grid_2d(
            data,
            lon,
            lat,
            x_out=x_out,
            y_out=y_out,
            resolution=tuple(resolution),
        )
        sweep_grids.append(
            _cinrad_layer_to_meteva(
                gridded,
                x_out,
                y_out,
                field_name=out_name,
                cinrad_file=radar_file,
                level=float(elev),
                units=units,
                member=member,
                time=scan_time,
            )
        )

    volume = _stack_gridded_sweeps(sweep_grids, level_coords)
    volume.name = out_name
    _apply_cinrad_grid_attrs(volume, radar_file)
    alt = float(getattr(radar_file, "radarheight", 0.0) or 0.0)
    volume.attrs["site_alt_m"] = alt
    return volume


def gridify_standard_fields(
    radar_file,
    *,
    field_names: Sequence[str] = DEFAULT_STANDARD_GRID_FIELDS,
    resolution: Sequence[int] = (1000, 1000),
    sweep: int = 0,
    drange=None,
):
    """标准体积 → 指定仰角 meb 单层网格字典（缺场则跳过）。"""
    volumes = {}
    levels = {}
    for name in field_names:
        product = str(name).upper()
        if not radar_file.available_tilt(product):
            continue
        vol = standard_field_to_meteva_volume(
            radar_file,
            product,
            resolution=resolution,
            drange=drange,
        )
        volumes[product] = vol
        levels[product] = select_grid_level(vol, int(sweep))
    return levels, volumes


def select_grid_level(grid_data: xr.DataArray, level_index: int = 0) -> xr.DataArray:
    """从 meteva 网格中取出指定 ``level`` 层（例如某一仰角 PPI）。"""
    normalized = meb.checkout_griddata(grid_data, is_single=False)
    nlevel = int(normalized.sizes["level"])
    idx = int(level_index)
    if idx < 0 or idx >= nlevel:
        raise IndexError(f"level_index {idx} out of range for level size {nlevel}")
    return normalized.isel(level=[idx])


def pyart_field_to_meteva_volume(
    radar,
    field_name: str,
    *,
    resolution: Sequence[int] = (1000, 1000),
    cinrad_file=None,
):
    """将已质控（掩膜）的 Py-ART 场逐仰角 ``grid_2d`` 成 meteva 体扫网格。

    掩膜门点填 NaN 后再插值，避免被质控剔除的库点渗入网格。
    """
    if field_name not in radar.fields:
        raise KeyError(f"radar has no field {field_name!r}")
    if cinrad_file is None:
        raise ValueError("cinrad_file is required to attach site/frequency attrs")
    out_name, units = FIELD_META.get(field_name, (field_name, "1"))
    level_coords = _radar_level_coords(radar)
    member = _radar_site_member(radar)
    scan_time = _radar_scan_time(radar)

    field = radar.fields[field_name]["data"]
    gate_lon = np.asarray(radar.gate_longitude["data"], dtype=np.float64)
    gate_lat = np.asarray(radar.gate_latitude["data"], dtype=np.float64)

    x_out = y_out = None
    sweep_grids = []
    for isweep, elev in enumerate(level_coords["level_list"]):
        start = int(radar.sweep_start_ray_index["data"][isweep])
        end = int(radar.sweep_end_ray_index["data"][isweep])
        sl = slice(start, end + 1)
        data = np.ma.filled(np.ma.asarray(field[sl]), np.nan).astype(np.float32)
        lon = gate_lon[sl]
        lat = gate_lat[sl]
        gridded, x_out, y_out = grid_2d(
            data,
            lon,
            lat,
            x_out=x_out,
            y_out=y_out,
            resolution=tuple(resolution),
        )
        sweep_grids.append(
            _cinrad_layer_to_meteva(
                gridded,
                x_out,
                y_out,
                field_name=out_name,
                cinrad_file=cinrad_file,
                level=float(elev),
                units=units,
                member=member,
                time=scan_time,
            )
        )

    volume = _stack_gridded_sweeps(sweep_grids, level_coords)
    volume.name = out_name
    _apply_radar_attrs(volume, radar, cinrad_file=cinrad_file)
    return volume


def gridify_radar_fields(
    radar,
    cinrad_file,
    *,
    field_names: Sequence[str] = DEFAULT_QPE_GRID_FIELDS,
    resolution: Sequence[int] = (1000, 1000),
    sweep: int = 0,
):
    """质控后 ``Radar`` → 指定仰角的 meb 六维单层网格字典（缺场则跳过）。"""
    volumes = {}
    levels = {}
    for name in field_names:
        if name not in radar.fields:
            continue
        vol = pyart_field_to_meteva_volume(
            radar, name, resolution=resolution, cinrad_file=cinrad_file
        )
        volumes[name] = vol
        levels[name] = select_grid_level(vol, int(sweep))
    return levels, volumes
