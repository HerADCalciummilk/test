"""cinrad StandardData → Py-ART Radar 预处理（sweep 修正、方位去重）。"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from radar_qpe_retrieval.cli.cinrad_meb import cinrad_frequency_hz


# ==================== 雷达基数据转 Py-ART Radar 预处理函数 ====================

def _reinit_ray_geometry(radar):
    """Reset lazy gate geometry after ray/sweep layout changes."""
    radar.nrays = len(radar.azimuth["data"])
    radar.init_rays_per_sweep()
    radar.init_gate_x_y_z()
    radar.init_gate_longitude_latitude()
    radar.init_gate_altitude()


def _sync_sweep_metadata(radar, tilt_indices=None):
    """使 sweep 维元数据长度与 ``radar.nsweeps`` 一致（write_cfradial 需要）。"""
    n = radar.nsweeps
    if tilt_indices is not None:
        sel = np.asarray(list(tilt_indices), dtype=int)
    else:
        sel = np.arange(n)

    def _subset(dic):
        data = np.asarray(dic["data"])
        if data.shape[0] == n:
            return
        dic["data"] = data[sel]

    if radar.sweep_mode is not None:
        _subset(radar.sweep_mode)
    if radar.target_scan_rate is not None:
        _subset(radar.target_scan_rate)
    if radar.antenna_transition is not None:
        _subset(radar.antenna_transition)
    if radar.instrument_parameters:
        for key in ("nyquist_velocity", "unambiguous_range"):
            if key in radar.instrument_parameters:
                _subset(radar.instrument_parameters[key])


def _sync_time_length(radar):
    t = np.asarray(radar.time["data"])
    n = len(radar.azimuth["data"])
    if len(t) == n:
        return
    if len(t) > n:
        radar.time["data"] = t[:n]
    else:
        radar.time["data"] = np.pad(t, (0, n - len(t)), mode="edge")


def _attach_radar_frequency(radar, cinrad_file):
    """确保 Py-ART ``Radar`` 带有 ``instrument_parameters['frequency']``（Hz）。

    ``standard_data_to_pyart`` 生成的对象在某些 cinrad 数据上可能没有频率字段；
    迁移后的 meteva 链路会从 ``attrs['frequency']`` 自动选默认系数。为避免
    原算法链和插件/CLI 链因默认频段系数不同而偏离，这里统一从 cinrad 文件
    回填频率到 Py-ART ``Radar``。
    """
    freq_hz = cinrad_frequency_hz(cinrad_file)
    if freq_hz is None or not np.isfinite(freq_hz):
        return radar

    if radar.instrument_parameters is None:
        radar.instrument_parameters = {}

    existing = radar.instrument_parameters.get("frequency")
    if existing is not None:
        try:
            existing_data = np.asarray(existing.get("data"), dtype=np.float64).ravel()
        except Exception:
            existing_data = np.array([], dtype=np.float64)
        if existing_data.size and np.isfinite(existing_data[0]):
            return radar

    radar.instrument_parameters["frequency"] = {
        "data": np.array([freq_hz], dtype=np.float32),
        "units": "Hz",
        "long_name": "radar transmit frequency",
    }
    return radar


def repair_cinrad_pyart_sweep_indices(cinrad_file, radar, *, radius: int = 460):
    """修正 ``standard_data_to_pyart`` 的 sweep 索引，使其与 REF 各仰角射线数一致。"""
    tilts = list(cinrad_file.available_tilt("REF"))
    if not tilts:
        raise ValueError("cinrad 文件中没有 REF 仰角层")

    starts, ends = [], []
    offset = 0
    for nel in tilts:
        raw = cinrad_file.get_raw(nel, radius, "REF")
        arr = raw[0] if isinstance(raw, tuple) else raw
        n_ray = int(np.asarray(arr).shape[0])
        starts.append(offset)
        ends.append(offset + n_ray - 1)
        offset += n_ray

    radar.nsweeps = len(tilts)
    radar.sweep_start_ray_index["data"] = np.array(starts, dtype="int32")
    radar.sweep_end_ray_index["data"] = np.array(ends, dtype="int32")
    radar.sweep_number["data"] = np.arange(len(tilts), dtype="int32")
    radar.fixed_angle["data"] = np.array(
        [cinrad_file.el[nel] for nel in tilts], dtype="float32"
    )
    radar.azimuth["data"] = np.hstack(
        [cinrad_file.aux[nel]["azimuth"] for nel in tilts]
    )
    radar.elevation["data"] = np.hstack(
        [cinrad_file.aux[nel]["elevation"] for nel in tilts]
    )
    _sync_time_length(radar)
    _sync_sweep_metadata(radar, tilts)
    _reinit_ray_geometry(radar)
    return radar


def dedupe_sweep_azimuths(radar, *, atol: float = 1e-6):
    """按 sweep 去除重复方位角，满足 ``composite_reflectivity`` 对严格递增 az 的要求。"""
    field_names = [
        k
        for k, v in radar.fields.items()
        if v["data"].ndim >= 1 and v["data"].shape[0] == radar.nrays
    ]

    new_starts, new_ends, fixed_angles = [], [], []
    az_chunks, el_chunks, t_chunks = [], [], []
    f_chunks = {k: [] for k in field_names}
    offset = 0

    for sw in range(radar.nsweeps):
        s = int(radar.sweep_start_ray_index["data"][sw])
        e = int(radar.sweep_end_ray_index["data"][sw])
        sl = slice(s, e + 1)
        az = np.asarray(radar.azimuth["data"][sl], dtype=float)
        n_eff = len(az)
        if "reflectivity" in radar.fields:
            n_eff = min(n_eff, int(radar.fields["reflectivity"]["data"][sl].shape[0]))
        if n_eff == 0:
            continue

        az = az[:n_eff]
        order = np.argsort(az, kind="mergesort")
        az_sorted = az[order]
        keep = np.ones(n_eff, dtype=bool)
        if n_eff > 1:
            keep[1:] = np.diff(az_sorted) > atol
        idx = order[keep]
        n = len(idx)

        new_starts.append(offset)
        new_ends.append(offset + n - 1)
        fixed_angles.append(float(radar.fixed_angle["data"][sw]))
        offset += n

        az_chunks.append(radar.azimuth["data"][sl][:n_eff][idx])
        el_chunks.append(radar.elevation["data"][sl][:n_eff][idx])
        t_chunks.append(radar.time["data"][sl][:n_eff][idx])
        for k in field_names:
            chunk = radar.fields[k]["data"][sl][:n_eff][idx]
            if not isinstance(chunk, np.ma.MaskedArray):
                chunk = np.ma.asarray(chunk)
            f_chunks[k].append(chunk)

    radar.nsweeps = len(new_starts)
    radar.sweep_start_ray_index["data"] = np.array(new_starts, dtype="int32")
    radar.sweep_end_ray_index["data"] = np.array(new_ends, dtype="int32")
    radar.sweep_number["data"] = np.arange(len(new_starts), dtype="int32")
    radar.fixed_angle["data"] = np.array(fixed_angles, dtype="float32")
    radar.azimuth["data"] = np.hstack(az_chunks)
    radar.elevation["data"] = np.hstack(el_chunks)
    radar.time["data"] = np.hstack(t_chunks)
    for k in field_names:
        radar.fields[k]["data"] = np.ma.vstack(f_chunks[k])

    _sync_sweep_metadata(radar)
    _reinit_ray_geometry(radar)
    return radar


def needs_cinrad_sweep_repair(cinrad_file, radar) -> bool:
    tilts = list(cinrad_file.available_tilt("REF"))
    if len(tilts) != radar.nsweeps:
        return True
    if int(radar.fields["reflectivity"]["data"].shape[0]) != radar.nrays:
        return True
    for sw in range(radar.nsweeps):
        sl = slice(
            int(radar.sweep_start_ray_index["data"][sw]),
            int(radar.sweep_end_ray_index["data"][sw]) + 1,
        )
        z = radar.fields["reflectivity"]["data"][sl]
        az = radar.azimuth["data"][sl]
        if z.shape[0] != len(az):
            return True
    return False


def prepare_radar_for_composite_reflectivity(
    radar, cinrad_file=None, *, radius: int = 460, dedupe: bool = True
):
    """修正 sweep（若需要）并去重方位角，再调用 ``composite_reflectivity``。"""
    if cinrad_file is not None and needs_cinrad_sweep_repair(cinrad_file, radar):
        repair_cinrad_pyart_sweep_indices(cinrad_file, radar, radius=radius)
    if dedupe:
        dedupe_sweep_azimuths(radar)
    return radar


def load_cinrad_pyart_radar(path, *, radius: int = 460, prepare: bool = True, dedupe: bool = True):
    """从 cinrad 基数据读取并转为已预处理的 Py-ART ``Radar``。"""
    import cinrad
    from cinrad.io.export import standard_data_to_pyart

    cinrad_file = cinrad.io.StandardData(str(path))
    radar = standard_data_to_pyart(cinrad_file, radius=radius)
    if prepare:
        radar = prepare_radar_for_composite_reflectivity(
            radar, cinrad_file=cinrad_file, radius=radius, dedupe=dedupe
        )
    radar = _attach_radar_frequency(radar, cinrad_file)
    return cinrad_file, radar


# ==================== 门点采样与掩膜处理函数 ====================

def sample_latlon_field_at_gates(
    field_2d,
    lat_1d,
    lon_1d,
    gate_lat,
    gate_lon,
    *,
    method: str = "nearest",
):
    """在规则经纬度网格上对雷达门点坐标采样。"""
    from scipy.interpolate import RegularGridInterpolator

    values = np.asarray(field_2d, dtype=np.float64)
    lat_axis = np.asarray(lat_1d, dtype=np.float64)
    lon_axis = np.asarray(lon_1d, dtype=np.float64)
    if lat_axis.size > 1 and lat_axis[0] > lat_axis[-1]:
        lat_axis = lat_axis[::-1]
        values = values[::-1, :]
    if lon_axis.size > 1 and lon_axis[0] > lon_axis[-1]:
        lon_axis = lon_axis[::-1]
        values = values[:, ::-1]
    interp = RegularGridInterpolator(
        (lat_axis, lon_axis),
        values,
        method=method,
        bounds_error=False,
        fill_value=np.nan,
    )
    sample_points = np.column_stack(
        [np.asarray(gate_lat, dtype=np.float64).ravel(), np.asarray(gate_lon, dtype=np.float64).ravel()]
    )
    return interp(sample_points).reshape(np.asarray(gate_lat).shape).astype(np.float32)


def gate_excluded_from_latlon_qc_mask(
    gate_lat: np.ndarray,
    gate_lon: np.ndarray,
    gate_included: np.ndarray,
    lon_1d: np.ndarray,
    lat_1d: np.ndarray,
    target_shape: tuple[int, int],
    *,
    method: str = "nearest",
) -> np.ndarray:
    """在门点经纬度上采样 ``gate_included``，得到 ``target_shape`` 的排除掩膜。"""
    included = np.asarray(gate_included, dtype=bool)
    if included.ndim != 2:
        raise ValueError("gate_included must be a 2D (lat, lon) mask")

    nr, ng = int(target_shape[0]), int(target_shape[1])
    glat = np.asarray(gate_lat, dtype=np.float64)[:nr, :ng]
    glon = np.asarray(gate_lon, dtype=np.float64)[:nr, :ng]
    included_at_gates = sample_latlon_field_at_gates(
        included.astype(np.float32),
        lat_1d,
        lon_1d,
        glat,
        glon,
        method=method,
    )
    keep = np.isfinite(included_at_gates) & (included_at_gates >= 0.5)
    return ~keep


_DEFAULT_RADAR_MASK_FIELDS = (
    "reflectivity",
    "specific_differential_phase",
    "cross_correlation_ratio",
    "differential_reflectivity",
    "velocity",
    "spectrum_width",
)


def apply_latlon_mask_to_pyart_radar(
    radar,
    gate_included: np.ndarray,
    lon_1d: np.ndarray,
    lat_1d: np.ndarray,
    field_names: Sequence[str] | None = None,
    *,
    method: str = "nearest",
) -> np.ndarray:
    """将 CREF QC 的 2D ``gate_included`` 掩膜应用到 Py-ART ``Radar`` 各门点场。"""
    gate_lon = np.asarray(radar.gate_longitude["data"], dtype=np.float64)
    gate_lat = np.asarray(radar.gate_latitude["data"], dtype=np.float64)
    gate_shape = gate_lat.shape

    if field_names is None:
        field_names = [name for name in _DEFAULT_RADAR_MASK_FIELDS if name in radar.fields]
    if not field_names:
        raise ValueError("no radar fields selected for lat/lon QC mask")

    for fname in field_names:
        if fname not in radar.fields:
            continue
        data = radar.fields[fname]["data"]
        exclude = gate_excluded_from_latlon_qc_mask(
            gate_lat,
            gate_lon,
            gate_included,
            lon_1d,
            lat_1d,
            data.shape,
            method=method,
        )
        if not isinstance(data, np.ma.MaskedArray):
            data = np.ma.asarray(data)
        else:
            data = data.copy()
        data.mask = np.logical_or(np.asarray(data.mask), exclude)
        radar.fields[fname]["data"] = data

    return gate_excluded_from_latlon_qc_mask(
        gate_lat,
        gate_lon,
        gate_included,
        lon_1d,
        lat_1d,
        gate_shape,
        method=method,
    )


# ==================== quick_cr 到 Radar 场填值函数 ====================

def fill_pyart_radar_from_quick_cr(
    cr_ds,
    radar,
    field_name: str = "composite_reflectivity",
    sweep_index: int = 0,
    *,
    method: str = "nearest",
):
    """用 ``quick_cr`` 的 CR(dBZ) 覆盖 Py-ART ``Radar`` 指定场（保持门点几何不变）。

    仅替换反射率数值，不转回极坐标；原算法 ``est_rain_rate_*`` 仍在门点经纬度上
    使用与插件相同的 cinrad 组合反射率输入。
    """
    if field_name not in radar.fields:
        raise KeyError(f"radar has no field {field_name!r}")

    sweep_index = int(sweep_index)
    start = int(radar.sweep_start_ray_index["data"][sweep_index])
    end = int(radar.sweep_end_ray_index["data"][sweep_index])
    sweep_slice = slice(start, end + 1)

    gate_lon = np.asarray(radar.gate_longitude["data"], dtype=np.float64)
    gate_lat = np.asarray(radar.gate_latitude["data"], dtype=np.float64)
    if gate_lon.ndim > 1:
        gate_lon = gate_lon[sweep_slice]
        gate_lat = gate_lat[sweep_slice]

    cr = np.asarray(cr_ds["CR"].values, dtype=np.float64)
    lat = np.asarray(cr_ds["latitude"].values, dtype=np.float64)
    lon = np.asarray(cr_ds["longitude"].values, dtype=np.float64)
    dbz = sample_latlon_field_at_gates(
        cr, lat, lon, gate_lat, gate_lon, method=method,
    )

    field = radar.fields[field_name]
    target = field["data"][sweep_slice]
    dbz_2d = np.asarray(dbz, dtype=target.dtype).reshape(target.shape)
    field["data"][sweep_slice] = np.ma.masked_invalid(dbz_2d)
    return radar
