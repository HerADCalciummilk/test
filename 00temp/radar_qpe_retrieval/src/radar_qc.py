# -*- coding: utf-8 -*-
"""极坐标雷达质控插件（Py-ART ``Radar`` + ``GateFilter`` + meb 网格）。

职责边界
--------
- 本模块：吃内存中的 ``Radar`` 与可选 DEM 高度网格，产出 ``GateFilter``、
  写回各场掩膜，并（在提供 ``cinrad_file`` 时）将质控后要素六维网格化，
  得到可直接供 ``QPEPlugin`` 使用的 meb 场。
- 不读基数据 / DEM 文件；路径 I/O 在 ``cli.polar_qc``。

质控环顺序（与业务约定一致）
----------------------------
无效库 / 天线过渡 → 反射率阈值 → ρhv →（可选）ZDR →
ΦDP/KDP 沿径向纹理 →（可选）DEM 波束遮挡 →
（可选）衰减：估比衰减 A + 订正 Z → 斑点剔除 → 六维网格化。

衰减环为**订正**（改数值 / 新增场），不是 GateFilter 剔除。
基数据通常无现成 A；本环用 Z-PHI 估 ``specific_attenuation``，
供后续 QPE ``method=a/za/hydro``，并把路径衰减补回反射率。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import xarray as xr

from radar_qpe_retrieval.src.polar_grid import (
    DEFAULT_QPE_GRID_FIELDS,
    gridify_radar_fields,
)
from radar_qpe_retrieval.utils.base_plugin import BasePlugin


@dataclass
class PolarQCResult:
    """质控 + 网格化结果（可直接喂 ``QPEPlugin``）。

    Attributes
    ----------
    refl, kdp, att :
        指定仰角的 meb 六维单层网格；缺场时为 ``None``。
    radar, gatefilter :
        写回掩膜后的极坐标体扫与门控。
    volumes :
        各场完整体扫六维网格（``level`` = 各仰角）。
    """

    refl: xr.DataArray | None
    kdp: xr.DataArray | None
    att: xr.DataArray | None
    radar: object
    gatefilter: object
    volumes: dict

# 写回掩膜时只动 QPE 主路径用到的场。
# 部分体扫里速度等场射线数与 GateFilter 不一致，默认跳过以免报错。
_DEFAULT_MASK_FIELDS = (
    "reflectivity",
    "specific_differential_phase",
    "cross_correlation_ratio",
    "specific_attenuation",
    "corrected_reflectivity",
)


def apply_gatefilter_to_radar_fields(
    radar,
    gatefilter,
    field_names: Sequence[str] | None = None,
    *,
    skip_mismatched: bool = True,
):
    """将 ``GateFilter`` 排除门点并入各场的 ``MaskedArray`` 掩膜（就地修改）。

    Parameters
    ----------
    field_names :
        要写回的场名；默认 ``_DEFAULT_MASK_FIELDS`` 中实际存在者。
    skip_mismatched :
        场与 ``gate_excluded`` 形状不一致时跳过（True）或抛错（False）。
    """
    if field_names is None:
        field_names = [n for n in _DEFAULT_MASK_FIELDS if n in radar.fields]
    excluded = np.asarray(gatefilter.gate_excluded, dtype=bool)
    for name in field_names:
        if name not in radar.fields:
            continue
        data = radar.fields[name]["data"]
        if excluded.shape != np.shape(data):
            if skip_mismatched:
                continue
            raise ValueError(
                f"gatefilter shape {excluded.shape} must match field {name!r} "
                f"shape {np.shape(data)}"
            )
        # 复制后再改 mask，避免改到 Py-ART 内部视图
        if not isinstance(data, np.ma.MaskedArray):
            data = np.ma.asarray(data)
        else:
            data = data.copy()
        data.mask = np.logical_or(np.asarray(data.mask), excluded)
        radar.fields[name]["data"] = data
    return radar


def dem_grid_to_arrays(dem) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """meb 高度网格 → ``(hgt_2d, lat_1d, lon_1d)``（米；lat/lon 严格递增）。"""
    if dem is None:
        raise ValueError("dem is None")
    da = dem
    # 压掉长度为 1 的前导维，保留 lat/lon
    for dim in ("member", "level", "time", "dtime"):
        if hasattr(da, "dims") and dim in da.dims and int(da.sizes[dim]) == 1:
            da = da.isel({dim: 0})
    if not hasattr(da, "lat") or not hasattr(da, "lon"):
        raise ValueError("dem must be a grid with lat/lon coordinates")
    lat = np.asarray(da["lat"].values, dtype=np.float64)
    lon = np.asarray(da["lon"].values, dtype=np.float64)
    hgt = np.asarray(np.squeeze(da.values), dtype=np.float32)
    if hgt.ndim != 2:
        raise ValueError(f"dem height must be 2-D after squeeze, got shape {hgt.shape}")
    if lat.size < 2 or lon.size < 2:
        raise ValueError("dem lat/lon must each have at least 2 points")
    if hgt.shape != (lat.size, lon.size):
        # 少数场可能是 (lon, lat)；按坐标长度对齐
        if hgt.shape == (lon.size, lat.size):
            hgt = hgt.T
        else:
            raise ValueError(
                f"dem height shape {hgt.shape} incompatible with lat={lat.size}, lon={lon.size}"
            )
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        hgt = hgt[::-1, :]
    if lon[0] > lon[-1]:
        lon = lon[::-1]
        hgt = hgt[:, ::-1]
    return hgt, lat, lon


def ensure_dem_covers_radar(radar, dem_lat: np.ndarray, dem_lon: np.ndarray) -> None:
    """检查 DEM 经纬范围是否覆盖雷达库点；不达标则报错（不做裁剪）。"""
    gate_lat = np.asarray(radar.gate_latitude["data"], dtype=np.float64)
    gate_lon = np.asarray(radar.gate_longitude["data"], dtype=np.float64)
    finite = np.isfinite(gate_lat) & np.isfinite(gate_lon)
    if not finite.any():
        raise ValueError("radar has no finite gate lat/lon for DEM coverage check")
    lat_min = float(np.nanmin(gate_lat[finite]))
    lat_max = float(np.nanmax(gate_lat[finite]))
    lon_min = float(np.nanmin(gate_lon[finite]))
    lon_max = float(np.nanmax(gate_lon[finite]))
    dlat0, dlat1 = float(np.min(dem_lat)), float(np.max(dem_lat))
    dlon0, dlon1 = float(np.min(dem_lon)), float(np.max(dem_lon))
    if lat_min < dlat0 or lat_max > dlat1 or lon_min < dlon0 or lon_max > dlon1:
        raise ValueError(
            "DEM lat/lon range does not cover radar gates: "
            f"gates lat[{lat_min:.4f},{lat_max:.4f}] lon[{lon_min:.4f},{lon_max:.4f}], "
            f"DEM lat[{dlat0:.4f},{dlat1:.4f}] lon[{dlon0:.4f},{dlon1:.4f}]"
        )


def compute_beam_blockage_mask(
    radar,
    dem_hgt: np.ndarray,
    dem_lat: np.ndarray,
    dem_lon: np.ndarray,
    *,
    min_clearance_m: float = 0.0,
    propagate_along_ray: bool = True,
    min_range_m: float = 2000.0,
) -> np.ndarray:
    """几何波束遮挡掩膜：地形高度 ≥ 波束高度 − 净空 则判遮挡。

    将 DEM 双线性插值到每个库点 (lat, lon)，与 ``gate_altitude`` 比较。
    ``dem_lat`` / ``dem_lon`` 须严格递增。

    Parameters
    ----------
    dem_hgt : (nlat, nlon)
        海拔（米）；经纬范围须覆盖雷达库点（见 ``ensure_dem_covers_radar``）。
    min_clearance_m :
        波束相对地形的最小净空（米）；0 表示地形触及波束中心即遮挡。
    propagate_along_ray :
        True 时沿径向一旦遮挡，更远库点全部遮挡（地形挡后无回波）。
    min_range_m :
        近站盲区（米）。站址 DEM 常略高于第 1 个库点波束高度，若参与判据并
        ``propagate_along_ray``，会把整条径向误判为遮挡；默认跳过 2 km 内库点。

    Returns
    -------
    blocked : bool ndarray, shape = (nrays, ngates)
    """
    from scipy.interpolate import RegularGridInterpolator

    ensure_dem_covers_radar(radar, dem_lat, dem_lon)

    gate_lat = np.asarray(radar.gate_latitude["data"], dtype=np.float64)
    gate_lon = np.asarray(radar.gate_longitude["data"], dtype=np.float64)
    gate_alt = np.asarray(radar.gate_altitude["data"], dtype=np.float64)
    rng = np.asarray(radar.range["data"], dtype=np.float64)
    if gate_alt.shape != gate_lat.shape:
        # 少数导出缺 altitude：4/3 等效地球半径近似波束高度（米）
        elev = np.asarray(radar.elevation["data"], dtype=np.float64)[:, None]
        site_alt = float(np.asarray(radar.altitude["data"]).ravel()[0])
        re = 6371000.0 * 4.0 / 3.0
        gate_alt = (
            site_alt
            + np.sin(np.deg2rad(elev)) * rng[None, :]
            + (rng[None, :] ** 2) / (2.0 * re)
        )

    interp = RegularGridInterpolator(
        (np.asarray(dem_lat, dtype=np.float64), np.asarray(dem_lon, dtype=np.float64)),
        np.asarray(dem_hgt, dtype=np.float64),
        method="linear",
        bounds_error=False,
        fill_value=np.nan,  # 域外不判遮挡
    )
    pts = np.column_stack([gate_lat.ravel(), gate_lon.ravel()])
    dem_gates = interp(pts).reshape(gate_lat.shape).astype(np.float32)
    blocked = np.isfinite(dem_gates) & (
        dem_gates >= (gate_alt.astype(np.float32) - float(min_clearance_m))
    )
    # 近站库点不参与遮挡种子，避免站址 DEM 微差沿径向全灭
    near = rng < float(min_range_m)
    if near.any():
        blocked = blocked.copy()
        blocked[:, near] = False
    if propagate_along_ray:
        # axis=1 为库点方向（近→远）
        blocked = np.logical_or.accumulate(blocked, axis=1)
    return blocked


class PolarRadarQCPlugin(BasePlugin):
    """极坐标体扫质控 + 质控后要素六维网格化。

    DEM 在 ``process(..., dem=...)`` 传入（已读入的 meb 高度网格，米；不接受路径）。
    有 ``dem`` 则做波束遮挡（并检查经纬是否覆盖库点）；不传则跳过。
    CLI 可用 ``meb.read_griddata_from_nc(dem_path)`` 读后传入。

    ``process(radar, cinrad_file=..., dem=...)`` 返回 ``PolarQCResult``（``refl`` /
    ``kdp`` / ``att`` 已为指定仰角 meb 六维场，可直接给 ``QPEPlugin``）。
    仅 ``process(radar)`` 时保持兼容，返回 ``(radar, gatefilter)``。
    """

    def __init__(
        self,
        *,
        # --- 场名 ---
        refl_field: str = "reflectivity",
        rho_field: str = "cross_correlation_ratio",
        zdr_field: str = "differential_reflectivity",
        phidp_field: str = "differential_phase",
        kdp_field: str = "specific_differential_phase",
        # --- 反射率 / ρhv ---
        min_refl_dbz: float = 15.0,
        max_refl_dbz: float = 80.0,
        min_rho: float = 0.85,
        # --- ZDR 联合（杂波区 ZDR 常异常偏大/偏小）---
        use_zdr: bool = True,
        min_zdr_db: float = -4.0,
        max_zdr_db: float = 8.0,
        # --- ΦDP / KDP 沿径向纹理（高纹理多为地物/噪声）---
        use_phidp_texture: bool = True,
        phidp_texture_thresh: float = 20.0,
        phidp_texture_window: int = 7,
        use_kdp_texture: bool = True,
        kdp_texture_thresh: float = 3.0,
        kdp_texture_window: int = 7,
        # --- DEM 波束遮挡阈值（是否启用由 process 是否传入 dem 决定）---
        blockage_clearance_m: float = 0.0,
        blockage_min_range_m: float = 2000.0,
        # --- 衰减订正（Z-PHI：估 A + 订正 Z；基数据无 A 时由此产生）---
        use_attenuation_correction: bool = True,
        attenuation_fzl_m: float = 4000.0,
        attenuation_doc: int = 15,
        spec_at_field: str = "specific_attenuation",
        pia_field: str = "path_integrated_attenuation",
        corr_refl_field: str = "corrected_reflectivity",
        replace_refl_with_corrected: bool = True,
        # --- 六维网格化（供 QPE）---
        resolution: Sequence[int] = (1000, 1000),
        sweep: int = 0,
        grid_fields: Sequence[str] | None = None,
        # --- 其它 ---
        exclude_transition: bool = True,
        despeckle: bool = True,
        despeckle_size: int = 15,
        apply_mask: bool = True,
        mask_fields: Sequence[str] | None = None,
    ):
        self.refl_field = refl_field
        self.rho_field = rho_field
        self.zdr_field = zdr_field
        self.phidp_field = phidp_field
        self.kdp_field = kdp_field
        self.min_refl_dbz = float(min_refl_dbz)
        self.max_refl_dbz = float(max_refl_dbz)
        self.min_rho = float(min_rho)
        self.use_zdr = bool(use_zdr)
        self.min_zdr_db = float(min_zdr_db)
        self.max_zdr_db = float(max_zdr_db)
        self.use_phidp_texture = bool(use_phidp_texture)
        self.phidp_texture_thresh = float(phidp_texture_thresh)
        self.phidp_texture_window = int(phidp_texture_window)
        self.use_kdp_texture = bool(use_kdp_texture)
        self.kdp_texture_thresh = float(kdp_texture_thresh)
        self.kdp_texture_window = int(kdp_texture_window)
        self.blockage_clearance_m = float(blockage_clearance_m)
        self.blockage_min_range_m = float(blockage_min_range_m)
        self.use_attenuation_correction = bool(use_attenuation_correction)
        self.attenuation_fzl_m = float(attenuation_fzl_m)
        self.attenuation_doc = int(attenuation_doc)
        self.spec_at_field = str(spec_at_field)
        self.pia_field = str(pia_field)
        self.corr_refl_field = str(corr_refl_field)
        self.replace_refl_with_corrected = bool(replace_refl_with_corrected)
        self.resolution = tuple(int(v) for v in resolution)
        self.sweep = int(sweep)
        self.grid_fields = (
            tuple(grid_fields)
            if grid_fields is not None
            else DEFAULT_QPE_GRID_FIELDS
        )
        self.exclude_transition = bool(exclude_transition)
        self.despeckle = bool(despeckle)
        self.despeckle_size = int(despeckle_size)
        self.apply_mask = bool(apply_mask)
        self.mask_fields = mask_fields

    def _apply_attenuation_correction(self, radar, gatefilter):
        """Z-PHI：估算比衰减 A、路径积分衰减 PIA，并订正反射率。

        使用 ``calculate_attenuation_zphi``（``temp_ref='fixed_fzl'``）。
        系数在未显式给定时由 Py-ART 按雷达频率选取。
        写出场：``spec_at_field`` / ``pia_field`` / ``corr_refl_field``；
        若 ``replace_refl_with_corrected``，则把订正后的 Z 写回 ``refl_field``，
        原始 Z 备份为 ``reflectivity_uncorrected``。
        """
        if self.phidp_field not in radar.fields:
            return radar
        from pyart.correct import calculate_attenuation_zphi

        zdr_field = self.zdr_field if self.zdr_field in radar.fields else None
        spec_at, pia, cor_z, *_rest = calculate_attenuation_zphi(
            radar,
            doc=self.attenuation_doc,
            fzl=self.attenuation_fzl_m,
            gatefilter=gatefilter,
            refl_field=self.refl_field,
            phidp_field=self.phidp_field,
            zdr_field=zdr_field,
            spec_at_field=self.spec_at_field,
            pia_field=self.pia_field,
            corr_refl_field=self.corr_refl_field,
            temp_ref="fixed_fzl",
        )
        for name, field_dict in (
            (self.spec_at_field, spec_at),
            (self.pia_field, pia),
            (self.corr_refl_field, cor_z),
        ):
            if name in radar.fields:
                del radar.fields[name]
            radar.add_field(name, field_dict, replace_existing=True)

        if self.replace_refl_with_corrected:
            backup = "reflectivity_uncorrected"
            if backup not in radar.fields:
                orig = dict(radar.fields[self.refl_field])
                orig["data"] = np.ma.asarray(
                    radar.fields[self.refl_field]["data"], dtype=np.float32
                ).copy()
                radar.add_field(backup, orig, replace_existing=False)
            # 订正后的 Z 作为后续 QPE 主反射率
            radar.fields[self.refl_field]["data"] = np.ma.asarray(
                cor_z["data"], dtype=np.float32
            ).copy()
        return radar

    def _exclude_texture(
        self,
        radar,
        gatefilter,
        field_name: str,
        thresh: float,
        window: int,
        tex_name: str,
    ):
        """沿径向计算纹理，高于 ``thresh`` 的门点写入 GateFilter。

        纹理场以 ``tex_name`` 临时挂到 ``radar.fields``，供
        ``exclude_above`` 使用（Py-ART 要求场名存在于 Radar）。
        """
        if field_name not in radar.fields:
            return gatefilter
        from pyart.util import texture_along_ray

        tex = texture_along_ray(radar, field_name, wind_size=int(window))
        # 不同 Py-ART 版本可能返回 field dict 或 MaskedArray
        if isinstance(tex, dict) and "data" in tex:
            field_dict = tex
        else:
            field_dict = {
                "data": np.ma.asarray(tex, dtype=np.float32),
                "units": "1",
                "long_name": f"texture of {field_name}",
            }
        if tex_name in radar.fields:
            del radar.fields[tex_name]
        radar.add_field(tex_name, field_dict, replace_existing=True)
        gatefilter.exclude_above(tex_name, float(thresh))
        return gatefilter

    def process(self, radar, cinrad_file=None, dem=None):
        """对 ``radar`` 按约定顺序做极坐标质控，可选六维网格化。

        Parameters
        ----------
        radar :
            Py-ART ``Radar``。
        cinrad_file :
            对应 CINRAD 基数据对象。传入时做质控后要素网格化，返回
            ``PolarQCResult``（``refl`` / ``kdp`` / ``att`` 可直接给 QPE）；
            为 ``None`` 时仅返回 ``(radar, gatefilter)``，兼容旧调用。
        dem :
            可选 meb 高度网格（米）。传入则做波束遮挡；省略则跳过。

        Returns
        -------
        PolarQCResult or (radar, gatefilter)
        """
        radar, gatefilter = self._run_polar_qc(radar, dem=dem)
        if cinrad_file is None:
            return radar, gatefilter

        levels, volumes = gridify_radar_fields(
            radar,
            cinrad_file,
            field_names=self.grid_fields,
            resolution=self.resolution,
            sweep=self.sweep,
        )
        return PolarQCResult(
            refl=levels.get(self.refl_field),
            kdp=levels.get(self.kdp_field),
            att=levels.get(self.spec_at_field),
            radar=radar,
            gatefilter=gatefilter,
            volumes=volumes,
        )

    def _run_polar_qc(self, radar, dem=None):
        """极坐标门控主路径（不含网格化）。"""
        from pyart.filters import GateFilter

        if self.refl_field not in radar.fields:
            raise KeyError(f"radar has no field {self.refl_field!r}")

        gatefilter = GateFilter(radar)
        # 天线仰角过渡段（部分体扫无此元数据，失败则跳过）
        if self.exclude_transition:
            try:
                gatefilter.exclude_transition()
            except Exception:
                pass

        # 1) 无效 / 已有掩膜库
        gatefilter.exclude_invalid(self.refl_field)
        gatefilter.exclude_masked(self.refl_field)

        # 2) 反射率阈值：过弱偏噪/地物，过强常为异常
        gatefilter.exclude_below(self.refl_field, self.min_refl_dbz)
        gatefilter.exclude_outside(self.refl_field, 0.0, self.max_refl_dbz)

        # 3) ρhv：降水区通常较高，低值多非气象回波
        if self.rho_field in radar.fields:
            gatefilter.exclude_invalid(self.rho_field)
            gatefilter.exclude_masked(self.rho_field)
            gatefilter.exclude_below(self.rho_field, self.min_rho)

        # 4) ZDR 联合（场缺失则自动跳过）
        if self.use_zdr and self.zdr_field in radar.fields:
            gatefilter.exclude_invalid(self.zdr_field)
            gatefilter.exclude_outside(self.zdr_field, self.min_zdr_db, self.max_zdr_db)

        # 5) ΦDP / KDP 纹理杂波
        if self.use_phidp_texture:
            gatefilter = self._exclude_texture(
                radar,
                gatefilter,
                self.phidp_field,
                self.phidp_texture_thresh,
                self.phidp_texture_window,
                "_qc_phidp_texture",
            )
        if self.use_kdp_texture:
            gatefilter = self._exclude_texture(
                radar,
                gatefilter,
                self.kdp_field,
                self.kdp_texture_thresh,
                self.kdp_texture_window,
                "_qc_kdp_texture",
            )

        # 6) DEM 波束遮挡（有 dem 才做）
        if dem is not None:
            dem_hgt, dem_lat, dem_lon = dem_grid_to_arrays(dem)
            blocked = compute_beam_blockage_mask(
                radar,
                dem_hgt,
                dem_lat,
                dem_lon,
                min_clearance_m=self.blockage_clearance_m,
                min_range_m=self.blockage_min_range_m,
            )
            gatefilter.exclude_gates(blocked)

        # 7) 衰减订正：在门控之后估 A、订正 Z（斑点前，使碎斑清理作用在订正场上）
        if self.use_attenuation_correction:
            radar = self._apply_attenuation_correction(radar, gatefilter)

        # 8) 斑点放最后：在前述掩膜基础上清残余碎斑
        if self.despeckle:
            from pyart.correct import despeckle_field

            gatefilter = despeckle_field(
                radar,
                self.refl_field,
                gatefilter=gatefilter,
                size=self.despeckle_size,
                threshold=self.min_refl_dbz,
            )

        if self.apply_mask:
            apply_gatefilter_to_radar_fields(
                radar, gatefilter, field_names=self.mask_fields
            )

        return radar, gatefilter
