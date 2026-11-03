"""cinrad StandardData/quick_cr → meteva_base.grid_data。

本模块涵盖三类能力：
1) 极坐标/单层 PPI → 规则经纬度 ``meteva_base.grid_data``；
2) 多仰角体扫拼接与 NetCDF 落盘；
3) CREF 质量控制与掩膜应用（供 QPE 预处理流程使用）。

NetCDF 落盘请使用 :func:`save_meteva_grid_to_netcdf`（float32 + CF 缺测值）；
避免直接使用 ``meteva_base.write_griddata_to_nc`` 的默认 int32 缩放，
否则 NaN 可能显示为约 ``-2147483.6``。

与 :mod:`cinrad_pyart_prep` 的分工：
- ``cinrad_pyart_prep``：cinrad → Py-ART ``Radar``（原算法、门点坐标侧）
- ``cinrad_meb``：cinrad ``get_data`` / ``grid_2d`` / ``quick_cr`` → meteva 网格侧
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

import meteva_base as meb
import xarray as xr
from cinrad.calc import grid_2d


# ==================== 通用校验/落盘函数 ====================

def _same_lat_lon_grid(grid_a: xr.DataArray, grid_b: xr.DataArray, *, atol: float = 0.02) -> bool:
    """检查两幅 meteva 网格的 lat/lon 轴是否一致（忽略 level 等差异）。"""
    if grid_a.shape[-2:] != grid_b.shape[-2:]:
        return False
    return bool(
        np.allclose(grid_a.coords["lat"].values, grid_b.coords["lat"].values, atol=atol)
        and np.allclose(grid_a.coords["lon"].values, grid_b.coords["lon"].values, atol=atol)
    )

_CINRAD_DTYPE_VAR_MAP = {
    "REF": ("REF", "reflectivity", "dBZ"),
    "KDP": ("KDP", "specific_differential_phase", "deg/km"),
    "RHO": ("RHO", "cross_correlation_ratio", "1"),
}

# CF 惯例缺测填充值；避免 meteva ``write_griddata_to_nc`` 的 int32 缩放把 NaN 写成约 -2147483.6
_CF_NETCDF_FILL = np.float32(9.969209968386869e36)


def _check_same_horiz_coordinates(grd_list: list[xr.DataArray]) -> bool:
    """检查多层网格的水平坐标是否一致（不比较 ``level``）。"""
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
    """在多层 meteva 网格上写入仰角/高度元数据（``level`` 坐标为仰角，度）。"""
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


def _sanitize_grid_values_for_nc(values: np.ndarray) -> np.ndarray:
    """将 NaN/异常极值统一为 NetCDF 缺测填充值（float32）。"""
    arr = np.asarray(values, dtype=np.float32).copy()
    invalid = ~np.isfinite(arr)
    invalid |= np.abs(arr) >= np.float32(1e19)
    invalid |= arr <= np.float32(-1e6)
    invalid |= np.abs(arr + 2147483.648) < np.float32(1.0)
    arr[invalid] = _CF_NETCDF_FILL
    return arr


def save_meteva_grid_to_netcdf(
    grid_data: xr.DataArray,
    output_path=None,
    compression: bool = True,
    show: bool = False,
) -> Path:
    """保存 meteva 网格为 NetCDF（float32 + CF ``_FillValue``）。"""
    if output_path is None:
        raise TypeError("save_meteva_grid_to_netcdf requires output_path")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = meb.checkout_griddata(grid_data, is_single=False)
    var_name = normalized.name or "data0"
    out = normalized.copy()
    out.values = _sanitize_grid_values_for_nc(out.values)
    if not out.attrs.get("units"):
        out.attrs["units"] = ""
    out.attrs.pop("_FillValue", None)
    out.attrs.pop("missing_value", None)

    ds = out.to_dataset(name=var_name)
    encoding: dict = {}
    for v in ds.data_vars:
        ds[v].attrs.pop("_FillValue", None)
        ds[v].attrs.pop("missing_value", None)
        enc = {
            "dtype": "float32",
            "_FillValue": _CF_NETCDF_FILL,
            "missing_value": _CF_NETCDF_FILL,
        }
        if compression:
            enc["zlib"] = True
            enc["complevel"] = 4
        encoding[v] = enc

    ds.to_netcdf(str(output_path), encoding=encoding)
    if show:
        print(f"saved {output_path}")
    return output_path


# ==================== DataArray 提取单层网格函数 ====================

def select_grid_level(grid_data: xr.DataArray, level_index: int = 0) -> xr.DataArray:
    """从 meteva 网格中取出指定 ``level`` 层（例如某一仰角 PPI）。"""
    normalized = meb.checkout_griddata(grid_data, is_single=False)
    nlevel = int(normalized.sizes["level"])
    idx = int(level_index)
    if idx < 0 or idx >= nlevel:
        raise IndexError(f"level_index {idx} out of range for level size {nlevel}")
    return normalized.isel(level=[idx])


# ==================== 雷达基数据转 meteva_base 网格格式处理函数 ====================
# 调用关系与使用方式（本区块核心是“cinrad数据 -> meteva网格”）：
# 1) 体扫主入口（最顶层，notebook常用）
#    使用方法：
#      - 先用 cinrad 读取基数据文件（StandardData）
#      - 再调用 cinrad_dtype_to_meteva_volume(cinrad_file, dtype, ...)
#    内部流程：
#      cinrad_dtype_to_meteva_volume
#        -> build_cinrad_level_coords      # 生成 tilt/level 对应关系与仰角元数据
#        -> _cinrad_layer_to_meteva        # 每个仰角单层网格转为 level=1 的 meteva
#        -> _stack_gridded_sweeps          # 将多层拼成体扫（level 维）并写入层坐标属性
#
# 2) CREF/QC 支撑入口（给质量控制流程准备低仰角辅助场）
#    build_cref_qc_aux_grids_from_cinrad
#      -> cinrad_tilt_to_meteva_grid_aligned
#         （按 CREF 的 lat/lon 模板对齐生成低仰角 REF/RHO，供后续 gatefilter 使用）
#
# 3) CR 转换与绘图入口（quick_cr 路径）
#    使用方法：
#      - 先通过 cinrad quick_cr 得到组合反射率 Dataset
#      - 再调用 cinrad_cr_to_meteva_grid 转为 meteva 网格
#      - 如需绘图数组，再调用 meteva_grid_plot_arrays
#
def _stack_gridded_sweeps(
    sweep_grids: list[xr.DataArray],
    level_coords: dict,
) -> xr.DataArray:
    """将各仰角单层 meteva 网格沿 ``level`` 维拼成体扫网格。"""
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


def build_cinrad_level_coords(
    cinrad_file,
    dtype: str,
    *,
    range_km: int = 300,
) -> dict:
    """构造 cinrad 体扫的 ``level`` 坐标元数据。"""
    tilts = list(cinrad_file.available_tilt(dtype))
    if not tilts:
        raise ValueError(f"cinrad 文件中没有 {dtype} 仰角层")
    elevation_deg = np.array([float(cinrad_file.el[nel]) for nel in tilts], dtype=np.float64)
    site_alt = float(getattr(cinrad_file, "radarheight", 0.0))
    ref_range = float(range_km) * 1000.0
    height_m = site_alt + ref_range * np.sin(np.deg2rad(elevation_deg))
    return {
        "tilt_indices": tilts,
        "level_list": [float(v) for v in elevation_deg],
        "elevation_deg": elevation_deg,
        "height_m": height_m.astype(np.float64),
        "height_reference": f"site_alt + {range_km:g}km*sin(elevation)",
        "range_m_used": ref_range,
        "site_alt_m": site_alt,
    }


def cinrad_frequency_hz(cinrad_file) -> float | None:
    """从标准格式基数据站配置读取发射频率（Hz）。

    cinrad 解析头块 ``site_config.frequency``（单位 MHz，见 QX/T 653 站配置），
    并保存为 ``StandardData.wavelength``（厘米）。二者满足
    ``wavelength_cm = 3e8 / (frequency_MHz * 1e4)``。
    """
    wl_cm = getattr(cinrad_file, "wavelength", None)
    if wl_cm is None:
        return None
    wl_cm = float(wl_cm)
    if not np.isfinite(wl_cm) or wl_cm <= 0:
        return None
    return 3e8 / (wl_cm * 0.01)


def _apply_cinrad_grid_attrs(gdata: meb.grid_data, cinrad_file) -> None:
    """写入站点、扫描时间与频率等元数据（供 QPE / 水凝物等读取 ``attrs``）。"""
    gdata.attrs["site_code"] = str(getattr(cinrad_file, "code", None) or "RADAR")
    gdata.attrs["scan_time"] = str(pd.to_datetime(cinrad_file.scantime))
    freq_hz = cinrad_frequency_hz(cinrad_file)
    if freq_hz is not None:
        gdata.attrs["frequency"] = float(freq_hz)
        gdata.attrs["frequency_units"] = "Hz"
    if getattr(cinrad_file, "name", None):
        gdata.attrs["site_name"] = str(cinrad_file.name)
    lon = getattr(cinrad_file, "stationlon", None)
    lat = getattr(cinrad_file, "stationlat", None)
    if lon is not None:
        gdata.attrs["site_longitude"] = float(lon)
    if lat is not None:
        gdata.attrs["site_latitude"] = float(lat)


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
    """单层经纬度规则网格 → meteva ``grid_data``（6 维，level=1）。"""
    if len(lon_1d) < 2 or len(lat_1d) < 2:
        raise ValueError("grid_2d 输出经纬度维度过小")
    dlon = float(lon_1d[1] - lon_1d[0])
    dlat = float(lat_1d[1] - lat_1d[0])
    if time is None:
        time = pd.to_datetime(cinrad_file.scantime)
    member = member or str(getattr(cinrad_file, "code", None) or "RADAR")

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


def cinrad_dtype_to_meteva_volume(
    cinrad_file,
    dtype: str,
    *,
    range_km: int = 300,
    resolution: Sequence[int] = (1000, 1000),
    field_name: str | None = None,
    units: str | None = None,
):
    """逐仰角 ``get_data`` + ``grid_2d``，拼成带 ``level`` 维的 meteva 体扫网格。

    与 ``quick_cr`` 相同，在 cinrad 内完成极坐标 → 经纬度网格，无需 ``standard_data_to_pyart``。
    """
    if dtype not in _CINRAD_DTYPE_VAR_MAP:
        raise ValueError(f"不支持的 dtype: {dtype}")
    cinrad_var, default_name, default_units = _CINRAD_DTYPE_VAR_MAP[dtype]
    field_name = field_name or default_name
    units = units or default_units

    level_coords = build_cinrad_level_coords(cinrad_file, dtype, range_km=range_km)
    x_out = y_out = None
    sweep_grids = []

    for nel, elev in zip(level_coords["tilt_indices"], level_coords["level_list"]):
        ds = cinrad_file.get_data(nel, range_km, dtype)
        data = np.asarray(ds[cinrad_var].values, dtype=np.float32)
        lon = np.asarray(ds["longitude"].values, dtype=np.float64)
        lat = np.asarray(ds["latitude"].values, dtype=np.float64)
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
                field_name=field_name,
                cinrad_file=cinrad_file,
                level=elev,
                units=units,
            )
        )

    volume = _stack_gridded_sweeps(sweep_grids, level_coords)
    volume.name = field_name
    _apply_cinrad_grid_attrs(volume, cinrad_file)
    return volume, sweep_grids


def cinrad_tilt_to_meteva_grid_aligned(
    cinrad_file,
    dtype: str,
    tilt_index: int,
    template_grid: xr.DataArray,
    *,
    range_km: int = 300,
    field_name: str | None = None,
    units: str | None = None,
) -> meb.grid_data:
    """将指定仰角单层重采样到与 ``template_grid`` 相同的 lat/lon 网格。"""
    if dtype not in _CINRAD_DTYPE_VAR_MAP:
        raise ValueError(f"不支持的 dtype: {dtype}")
    cinrad_var, default_name, default_units = _CINRAD_DTYPE_VAR_MAP[dtype]
    field_name = field_name or default_name
    units = units or default_units

    tilts = list(cinrad_file.available_tilt(dtype))
    if not tilts:
        raise ValueError(f"cinrad 文件中没有 {dtype} 仰角层")
    tilt_index = int(tilt_index)
    if tilt_index < 0 or tilt_index >= len(tilts):
        raise ValueError(f"tilt_index {tilt_index} 超出 {dtype} 仰角范围")

    lon_1d = np.asarray(template_grid.coords["lon"].values, dtype=np.float64)
    lat_1d = np.asarray(template_grid.coords["lat"].values, dtype=np.float64)
    resolution = (int(lon_1d.size), int(lat_1d.size))

    nel = tilts[tilt_index]
    elev = float(cinrad_file.el[nel])
    ds = cinrad_file.get_data(nel, range_km, dtype)
    data = np.asarray(ds[cinrad_var].values, dtype=np.float32)
    lon = np.asarray(ds["longitude"].values, dtype=np.float64)
    lat = np.asarray(ds["latitude"].values, dtype=np.float64)
    gridded, _, _ = grid_2d(
        data,
        lon,
        lat,
        x_out=lon_1d,
        y_out=lat_1d,
        resolution=resolution,
    )
    return _cinrad_layer_to_meteva(
        gridded,
        lon_1d,
        lat_1d,
        field_name=field_name,
        cinrad_file=cinrad_file,
        level=elev,
        units=units,
    )


def cinrad_cr_to_meteva_grid(
    cr_ds,
    field_name: str = "composite_reflectivity",
    member: str | None = None,
    time=None,
    dtime: int = 0,
    level: float = 0.0,
    cinrad_file=None,
):
    """``quick_cr`` 的 Dataset → meteva ``grid_data``。"""
    data = np.asarray(cr_ds["CR"].values, dtype=np.float32)
    lat = np.asarray(cr_ds["latitude"].values, dtype=np.float64)
    lon = np.asarray(cr_ds["longitude"].values, dtype=np.float64)
    if lat.ndim != 1 or lon.ndim != 1:
        raise ValueError("quick_cr 需要 1D latitude/longitude 坐标")
    dlon = float(lon[1] - lon[0]) if len(lon) > 1 else 0.01
    dlat = float(lat[1] - lat[0]) if len(lat) > 1 else 0.01
    if time is None:
        time = pd.to_datetime(cr_ds.attrs.get("scan_time"))
    elif isinstance(time, str):
        time = pd.to_datetime(time)
    member = member or str(cr_ds.attrs.get("site_code", "RADAR"))
    grid = meb.grid(
        [float(lon.min()), float(lon.max()), dlon],
        [float(lat.min()), float(lat.max()), dlat],
        gtime=time,
        dtime_list=[int(dtime)],
        level_list=[float(level)],
        member_list=[member],
    )
    gdata = meb.grid_data(grid, data)
    gdata.name = field_name
    gdata.attrs["units"] = "dBZ"
    gdata.attrs["var_name"] = field_name
    gdata.attrs["data_name"] = member
    for key in (
        "site_code",
        "site_name",
        "site_longitude",
        "site_latitude",
        "scan_time",
        "elevation",
        "frequency",
        "frequency_units",
    ):
        if key in cr_ds.attrs:
            gdata.attrs[key] = cr_ds.attrs[key]
    if cinrad_file is not None:
        _apply_cinrad_grid_attrs(gdata, cinrad_file)
    return gdata


def meteva_grid_plot_arrays(meteva_grid):
    """从 meteva 网格提取绘图所需二维数据与经纬度数组。"""
    lon = np.asarray(meteva_grid.coords["lon"].values, dtype=np.float64)
    lat = np.asarray(meteva_grid.coords["lat"].values, dtype=np.float64)
    lon_2d, lat_2d = np.meshgrid(lon, lat)
    data_2d = np.asarray(meteva_grid.values, dtype=np.float32).squeeze()
    return data_2d, lon_2d, lat_2d, lon, lat


# ==================== 掩膜与质量控制处理函数 ====================

def apply_meteva_gate_mask(
    grid_data: xr.DataArray,
    gate_included: np.ndarray,
) -> xr.DataArray:
    """用 ``gate_included``（2D lat×lon，True 为保留）掩膜 meteva 网格。

    同一 2D 掩膜作用于 **所有** ``member/level/time/dtime`` 层（`values[..., lat, lon]`），
    不是只过滤某一个 ``level``。若只需单层，请先 ``select_grid_level`` 再掩膜。
    """
    included = np.asarray(gate_included, dtype=bool)
    if included.ndim != 2:
        raise ValueError("gate_included must be a 2D (lat, lon) mask")
    out = grid_data.copy()
    values = np.asarray(out.values, dtype=np.float32).copy()
    if values.shape[-2:] != included.shape:
        raise ValueError(
            f"gate_included shape {included.shape} must match grid plane {values.shape[-2:]}"
        )
    values[..., ~included] = np.nan
    out.values = values
    return out


def apply_cref_quality_gatefilter(
    cref_grid: xr.DataArray,
    *,
    refl_low: xr.DataArray | None = None,
    rho_low: xr.DataArray | None = None,
    min_refl_dbz: float = 15.0,
    min_rho: float = 0.85,
    min_cref_dbz: float = 15.0,
    max_dbz: float = 80.0,
):
    """对 CREF 网格应用 ``GridGateFilter``（低仰角 REF + RHO + CR 自身阈值）。

    返回
    ----
    cref_qc, gate_included
        过滤后的 CREF、2D 保留掩膜。
    """
    from radar_qpe_retrieval.utils.grid_gate_filter import GridGateFilter

    cref_grid = xr.DataArray(cref_grid) if not isinstance(cref_grid, xr.DataArray) else cref_grid
    if refl_low is not None and not _same_lat_lon_grid(cref_grid, refl_low):
        raise ValueError("cref_grid and refl_low must share the same lat/lon coordinates")
    if rho_low is not None and not _same_lat_lon_grid(cref_grid, rho_low):
        raise ValueError("cref_grid and rho_low must share the same lat/lon coordinates")

    gatefilter = GridGateFilter(cref_grid)
    gatefilter.exclude_invalid(cref_grid)
    gatefilter.exclude_masked(cref_grid)
    if min_cref_dbz is not None:
        gatefilter.exclude_below(cref_grid, float(min_cref_dbz))
    if max_dbz is not None:
        gatefilter.exclude_outside(cref_grid, 0.0, float(max_dbz))
    if refl_low is not None:
        gatefilter.exclude_invalid(refl_low)
        gatefilter.exclude_masked(refl_low)
        if min_refl_dbz is not None:
            gatefilter.exclude_below(refl_low, float(min_refl_dbz))
    if rho_low is not None:
        gatefilter.exclude_invalid(rho_low)
        gatefilter.exclude_masked(rho_low)
        if min_rho is not None:
            gatefilter.exclude_below(rho_low, float(min_rho))

    gate_included = np.asarray(gatefilter.gate_included, dtype=bool)
    cref_qc = apply_meteva_gate_mask(cref_grid, gate_included)
    cref_qc.attrs = dict(cref_grid.attrs)
    cref_qc.attrs["qc_gatefilter"] = "cref+low_refl+rho"
    return cref_qc, gate_included


def build_cref_qc_aux_grids_from_cinrad(
    cinrad_file,
    cref_grid: xr.DataArray,
    *,
    range_km: int = 300,
    max_low_tilt_deg: float = 2.0,
) -> tuple[meb.grid_data, meb.grid_data, int]:
    """生成与 CREF 对齐的低仰角 REF、RHO 网格。"""
    ref_tilts = list(cinrad_file.available_tilt("REF"))
    if not ref_tilts:
        raise ValueError("cinrad 文件中没有 REF 仰角层")
    ref_elev = np.asarray([float(cinrad_file.el[nel]) for nel in ref_tilts], dtype=np.float64)
    ref_candidates = np.where(ref_elev <= float(max_low_tilt_deg))[0]
    if ref_candidates.size == 0:
        low_idx = int(np.argmin(ref_elev))
    else:
        low_idx = int(ref_candidates[np.argmin(ref_elev[ref_candidates])])
    refl_low = cinrad_tilt_to_meteva_grid_aligned(
        cinrad_file, "REF", low_idx, cref_grid, range_km=range_km,
    )
    rho_low = None
    if list(cinrad_file.available_tilt("RHO")):
        rho_tilts = list(cinrad_file.available_tilt("RHO"))
        rho_idx = min(low_idx, len(rho_tilts) - 1)
        rho_low = cinrad_tilt_to_meteva_grid_aligned(
            cinrad_file, "RHO", rho_idx, cref_grid, range_km=range_km,
            field_name="cross_correlation_ratio",
        )
    return refl_low, rho_low, low_idx


def apply_cr_dataset_gate_mask(cr_ds, gate_included: np.ndarray):
    """将 2D 掩膜应用到 cinrad ``quick_cr`` 输出 ``CR`` 场。"""
    included = np.asarray(gate_included, dtype=bool)
    cr = np.asarray(cr_ds["CR"].values, dtype=np.float32).copy()
    if cr.shape != included.shape:
        raise ValueError(f"CR shape {cr.shape} must match gate mask {included.shape}")
    cr[~included] = np.nan
    out = cr_ds.copy(deep=True)
    out["CR"].values = cr
    return out


