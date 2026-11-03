#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""基于连通区域合并的速度退模糊算法。"""

from __future__ import annotations

import meteva_base as meb
import numpy as np
import xarray as xr

from radar_wind_dealiasing.utils.base_plugin import BasePlugin
from radar_wind_dealiasing.src.utils._geo_remap import (
    attach_gate_lonlat,
    build_latlon_griddata_from_template,
    infer_radar_location_from_attrs,
    infer_target_lonlat_grid,
    mask_outside_radar_coverage,
    remap_gate_data_to_latlon_grid,
)
from radar_wind_dealiasing.src.utils._common_dealias import (
    _as_ray_gate_excluded,
    _normalize_optional_grid,
    _parse_gatefilter,
    _parse_rays_wrap_around,
    _set_limits,
)
from radar_wind_dealiasing.src.utils._polar_volume import (
    _replace_polar_volume_values,
    parse_polar_volume_layout,
)
from radar_wind_dealiasing.src.utils._region_solver import _dealias_region_based_2d


class RegionDealiasPlugin(BasePlugin):
    """`dealias_region_based` 的插件封装。

    插件层只负责参数收口、输入转发和地理后处理，不重复实现核心
    退模糊逻辑。核心连通域展开、分段合并、参考速度锚定等步骤都
    仍然保留在 :func:`dealias_region_based` 中。

    插件额外提供的能力主要有两类：
    1. 统一接收 ``meteva_base`` 网格输入，并将过滤器与辅助参数转发给核心算法。
    2. 在需要时为结果补充经纬度信息，并重映射到规则经纬网格。
    """

    def __init__(
        self,
        interval_splits: int = 3,
        interval_limits=None,
        skip_between_rays: int = 100,
        skip_along_ray: int = 100,
        centered: bool = True,
        nyquist_velocity=None,
        gatefilter=False,
        min_ncp: float | None = 0.5,
        min_rhv: float | None = None,
        min_refl: float | None = -20.0,
        max_refl: float | None = 100.0,
        rays_wrap_around: bool | None = None,
        keep_original: bool = False,
        set_limits: bool = True,
        data_name: str = "corrected_velocity",
        attrs: dict | None = None,
        radar_lon: float | None = None,
        radar_lat: float | None = None,
        elevation_deg: float = 0.0,
        azimuth_deg=None,
        range_m=None,
        target_lon=None,
        target_lat=None,
        geo_method: str = "nearest",
        geo_resolution_deg: float | None = 0.01,
        geo_nlon: int | None = None,
        geo_nlat: int | None = None,
        auto_remap_to_latlon: bool = False,
    ) -> None:
        """初始化区域退模糊插件。

        参数
        ----
        interval_splits : int, optional
            Nyquist 区间划分数量。值越大，速度分段越细。
        interval_limits : array-like or None, optional
            自定义速度分段边界。若为 ``None``，则由 Nyquist 速度自动生成。
        skip_between_rays, skip_along_ray : int, optional
            区域连通判定时允许跨越的方位向和径向格点数。
        centered : bool, optional
            是否将最终圈数整体平移到以 0 为中心。
        nyquist_velocity : float, array-like or None, optional
            Nyquist 速度。可以是所有 sweep 共用的标量，也可以是逐
            sweep 数组。
        gatefilter : None, False or GridGateFilter, optional
            门限过滤器配置。
            ``False`` 表示不使用过滤器；
            ``None`` 表示由 ``refl``、``ncp``、``rhv`` 和阈值参数在内部构建；
            ``GridGateFilter`` 表示直接使用外部已构建好的过滤器。
        min_ncp, min_rhv, min_refl, max_refl : float or None, optional
            当 ``gatefilter=None`` 时，用于构建过滤器的阈值参数。
        rays_wrap_around : bool or None, optional
            方位向是否首尾相接。未指定时由输入网格属性自动判断。
        keep_original : bool, optional
            对于被过滤的格点，是否保留原始输入值。
        set_limits : bool, optional
            是否在结果属性中写入 ``valid_min`` 和 ``valid_max``。
        data_name : str, optional
            输出结果的数据名称。
        attrs : dict or None, optional
            需要附加到输出结果中的额外属性。
        radar_lon, radar_lat : float or None, optional
            雷达站点经纬度，用于后续地理重映射。
        elevation_deg : float, optional
            仰角，用于构造地理坐标时的局地几何近似。
        azimuth_deg : array-like or None, optional
            方位角坐标。若给定，可用于更精确地重建地理位置。
        range_m : array-like or None, optional
            径向距离坐标。单位应为米；若输入已有单位属性，也会按属性转换。
        target_lon, target_lat : array-like or None, optional
            目标经纬网格范围，用于指定重映射区域。
        geo_method : str, optional
            地理重映射方法，当前通常使用 ``nearest`` 或相近策略。
        geo_resolution_deg : float or None, optional
            目标经纬网格分辨率。若同时提供 ``geo_nlon`` / ``geo_nlat``，
            该参数可不使用。
        geo_nlon, geo_nlat : int or None, optional
            目标经纬网格的经向和纬向格点数。
        auto_remap_to_latlon : bool, optional
            是否在插件返回前自动重映射到规则经纬网格。
        """
        self.kwargs = {
            "interval_splits": interval_splits,
            "interval_limits": interval_limits,
            "skip_between_rays": skip_between_rays,
            "skip_along_ray": skip_along_ray,
            "centered": centered,
            "nyquist_velocity": nyquist_velocity,
            "gatefilter": gatefilter,
            "min_ncp": min_ncp,
            "min_rhv": min_rhv,
            "min_refl": min_refl,
            "max_refl": max_refl,
            "rays_wrap_around": rays_wrap_around,
            "keep_original": keep_original,
            "set_limits": set_limits,
            "data_name": data_name,
            "attrs": attrs,
            "radar_lon": radar_lon,
            "radar_lat": radar_lat,
            "elevation_deg": elevation_deg,
            "azimuth_deg": azimuth_deg,
            "range_m": range_m,
            "target_lon": target_lon,
            "target_lat": target_lat,
            "geo_method": geo_method,
            "geo_resolution_deg": geo_resolution_deg,
            "geo_nlon": geo_nlon,
            "geo_nlat": geo_nlat,
            "auto_remap_to_latlon": auto_remap_to_latlon,
        }

    def process(
        self,
        velocity: xr.DataArray,
        ref_velocity: xr.DataArray | None = None,
        refl: xr.DataArray | None = None,
        ncp: xr.DataArray | None = None,
        rhv: xr.DataArray | None = None,
    ) -> xr.DataArray:
        """执行退模糊并按需完成地理后处理。

        参数
        ----
        velocity : xr.DataArray
            待退模糊的速度场。
        ref_velocity : xr.DataArray or None, optional
            参考速度场，用于区域合并后的结果锚定。
        refl, ncp, rhv : xr.DataArray or None, optional
            用于构建网格过滤器的辅助物理量。

        返回
        ----
        xr.DataArray
            退模糊后的结果；如果开启了地理重映射，则返回规则经纬网格。
        """
        result = dealias_region_based(
            velocity=velocity,
            ref_velocity=ref_velocity,
            interval_splits=self.kwargs["interval_splits"],
            interval_limits=self.kwargs["interval_limits"],
            skip_between_rays=self.kwargs["skip_between_rays"],
            skip_along_ray=self.kwargs["skip_along_ray"],
            centered=self.kwargs["centered"],
            nyquist_velocity=self.kwargs["nyquist_velocity"],
            gatefilter=self.kwargs["gatefilter"],
            refl=refl,
            ncp=ncp,
            rhv=rhv,
            min_ncp=self.kwargs["min_ncp"],
            min_rhv=self.kwargs["min_rhv"],
            min_refl=self.kwargs["min_refl"],
            max_refl=self.kwargs["max_refl"],
            rays_wrap_around=self.kwargs["rays_wrap_around"],
            keep_original=self.kwargs["keep_original"],
            set_limits=self.kwargs["set_limits"],
            data_name=self.kwargs["data_name"],
            attrs=self.kwargs["attrs"],
        )
        return self._post_process_geo(result, source_grid=velocity)

    def _post_process_geo(self, result: xr.DataArray, source_grid: xr.DataArray | None = None) -> xr.DataArray:
        """为退模糊结果补充地理元信息，并按需重映射到经纬网格。"""
        radar_lon = self.kwargs["radar_lon"]
        radar_lat = self.kwargs["radar_lat"]
        geo_source = result.copy(deep=True)
        if source_grid is not None:
            enriched_attrs = dict(geo_source.attrs)
            for key in (
                "grid_axis_type",
                "azimuth_units",
                "range_units",
                "range_scale_to_m",
                "radar_lon",
                "radar_lat",
                "site_lon",
                "site_lat",
                "longitude",
                "latitude",
            ):
                if key in source_grid.attrs and key not in enriched_attrs:
                    enriched_attrs[key] = source_grid.attrs[key]
            geo_source.attrs = enriched_attrs
            for coord_name in ("lon", "lat"):
                if coord_name in source_grid.coords:
                    geo_source.coords[coord_name].attrs.update(
                        dict(getattr(source_grid.coords[coord_name], "attrs", {}))
                    )
        if radar_lon is None or radar_lat is None:
            inferred_lon, inferred_lat = infer_radar_location_from_attrs(geo_source)
            if (inferred_lon is None or inferred_lat is None) and source_grid is not None:
                source_like = xr.DataArray(
                    np.empty((1, 1, 1, 1, 1, 1), dtype=np.float32),
                    dims=("member", "level", "time", "dtime", "lat", "lon"),
                    coords={
                        "member": [0],
                        "level": [0],
                        "time": [0],
                        "dtime": [0],
                        "lat": [0],
                        "lon": [0],
                    },
                    attrs=dict(source_grid.attrs),
                )
                inferred_lon, inferred_lat = infer_radar_location_from_attrs(source_like)
            if radar_lon is None:
                radar_lon = inferred_lon
            if radar_lat is None:
                radar_lat = inferred_lat

        if radar_lon is None or radar_lat is None:
            return result

        attached = attach_gate_lonlat(
            geo_source,
            radar_lon=float(radar_lon),
            radar_lat=float(radar_lat),
            azimuth_deg=self.kwargs["azimuth_deg"],
            range_m=self.kwargs["range_m"],
            elevation_deg=self.kwargs["elevation_deg"],
        )

        if not (
            self.kwargs["auto_remap_to_latlon"]
            or (
                self.kwargs["target_lon"] is not None
                and self.kwargs["target_lat"] is not None
            )
        ):
            return attached

        resolved_target_lon, resolved_target_lat = infer_target_lonlat_grid(
            gate_lon=attached.coords["gate_lon"].values,
            gate_lat=attached.coords["gate_lat"].values,
            target_lon=self.kwargs["target_lon"],
            target_lat=self.kwargs["target_lat"],
            geo_resolution_deg=self.kwargs["geo_resolution_deg"],
            geo_nlon=self.kwargs["geo_nlon"],
            geo_nlat=self.kwargs["geo_nlat"],
        )
        layout = parse_polar_volume_layout(attached)
        level_results = []
        for sweep_slice, fixed_angle in zip(
            layout.sweep_slices,
            layout.fixed_angle,
        ):
            sweep_gate_lon = attached.coords["gate_lon"].values[
                sweep_slice,
                :,
            ]
            sweep_gate_lat = attached.coords["gate_lat"].values[
                sweep_slice,
                :,
            ]
            remapped_values = remap_gate_data_to_latlon_grid(
                values=attached.values[0, 0, 0, 0, sweep_slice, :],
                gate_lon=sweep_gate_lon,
                gate_lat=sweep_gate_lat,
                target_lon=resolved_target_lon,
                target_lat=resolved_target_lat,
                method=self.kwargs["geo_method"],
                missing_value=result.attrs.get("missing_value"),
                fill_value=result.attrs.get("_FillValue", np.nan),
            )
            remapped_values = mask_outside_radar_coverage(
                remapped_values,
                target_lon=resolved_target_lon,
                target_lat=resolved_target_lat,
                radar_lon=float(radar_lon),
                radar_lat=float(radar_lat),
                gate_lon=sweep_gate_lon,
                gate_lat=sweep_gate_lat,
                fill_value=result.attrs.get("_FillValue", np.nan),
            )
            level_result = build_latlon_griddata_from_template(
                attached,
                data_2d=remapped_values,
                target_lon=resolved_target_lon,
                target_lat=resolved_target_lat,
                data_name=attached.name,
            )
            level_results.append(
                level_result.assign_coords(level=[float(fixed_angle)])
            )

        remapped = xr.concat(level_results, dim="level")
        remapped.attrs.update(dict(attached.attrs))
        remapped.attrs["grid_axis_type"] = "latlon"
        remapped.attrs["level_coordinate"] = "elevation_deg"
        remapped.coords["level"].attrs.update(
            {
                "units": "degrees",
                "standard_name": "elevation_angle",
                "long_name": "radar fixed angle",
            }
        )
        return remapped


def dealias_region_based(
    velocity: xr.DataArray,
    ref_velocity: xr.DataArray | None = None,
    interval_splits: int = 3,
    interval_limits=None,
    skip_between_rays: int = 100,
    skip_along_ray: int = 100,
    centered: bool = True,
    nyquist_velocity=None,
    gatefilter=False,
    refl: xr.DataArray | None = None,
    ncp: xr.DataArray | None = None,
    rhv: xr.DataArray | None = None,
    min_ncp: float | None = 0.5,
    min_rhv: float | None = None,
    min_refl: float | None = -20.0,
    max_refl: float | None = 100.0,
    rays_wrap_around: bool | None = None,
    keep_original: bool = False,
    set_limits: bool = True,
    data_name: str = "corrected_velocity",
    attrs: dict | None = None,
):
    """基于 meteva_base 网格数据的基于区域雷达速度退模糊实现。

    参数
    ----
    velocity : xr.DataArray
        待退模糊的完整极坐标体扫。前四维长度均为 1，全部 sweep
        沿 ``lat``（ray）维连续拼接，并由属性记录 sweep 边界。
    ref_velocity : xr.DataArray or None, optional
        参考速度场。可用于在参考场存在时进行全局或分区锚定。
    interval_splits : int, optional
        Nyquist 区间划分数量。
    interval_limits : array-like or None, optional
        自定义速度分段边界。未给定时由 Nyquist 速度自动生成。
    skip_between_rays, skip_along_ray : int, optional
        区域连通判定时允许跳过的方位向与径向间隔。
    centered : bool, optional
        是否在最终结果中将各分段圈数整体居中到 0。
    nyquist_velocity : float, array-like or None, optional
        Nyquist 速度。可为所有 sweep 共用的标量，或逐 sweep 数组。
    gatefilter : None, False or GridGateFilter, optional
        输入门限过滤器。
        ``False`` 表示不使用过滤器；
        ``None`` 表示在函数内部根据 ``refl``、``ncp``、``rhv`` 等场构建；
        ``GridGateFilter`` 表示直接使用外部已构建好的过滤器。
    refl, ncp, rhv : xr.DataArray or None, optional
        当 ``gatefilter=None`` 时用于构建过滤器的辅助场。
    min_ncp, min_rhv, min_refl, max_refl : float or None, optional
        当 ``gatefilter=None`` 时用于构建过滤器的阈值。
    rays_wrap_around : bool or None, optional
        方位角是否首尾相接。未指定时由输入网格属性判断。
    keep_original : bool, optional
        对于被过滤的格点，是否保留原始输入值。
    set_limits : bool, optional
        是否在结果属性中写入 ``valid_min`` 与 ``valid_max``。
    data_name : str, optional
        输出数据名称。
    attrs : dict or None, optional
        需要附加到输出结果中的属性字典。

    返回
    ----
    xr.DataArray
        退模糊后的 meteva_base 网格数据。
    """
    # =====================================
    # 输入预处理
    #
    # 先规范输入网格，再统一处理缺测和填充值，避免这些元信息在
    # 后续分段展开时被误当成有效速度参与计算。
    # =====================================
    velocity_grid = meb.checkout_griddata(
        velocity,
        is_single=False,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    fill_value = float(np.float32(-9999.0))
    for key in ("_FillValue", "missing_value"):
        if key not in velocity_grid.attrs:
            continue
        try:
            fill_value = float(velocity_grid.attrs[key])
            break
        except (TypeError, ValueError):
            continue
    ref_velocity_grid = _normalize_optional_grid(
        ref_velocity,
        velocity_grid,
        "ref_velocity",
    )
    refl_grid = _normalize_optional_grid(refl, velocity_grid, "refl")
    ncp_grid = _normalize_optional_grid(ncp, velocity_grid, "ncp")
    rhv_grid = _normalize_optional_grid(rhv, velocity_grid, "rhv")

    layout = parse_polar_volume_layout(
        velocity_grid,
        nyquist_velocity=nyquist_velocity,
    )
    rays_wrap_around = _parse_rays_wrap_around(
        rays_wrap_around,
        velocity_grid,
    )

    # 全部 sweep 沿 ray 维连续拼接，二维求解器按边界逐 sweep 调用。
    corrected_values = np.array(velocity_grid.values, dtype=np.float32, copy=True)
    volume_gatefilter = _parse_gatefilter(
        gatefilter,
        velocity_grid,
        refl=refl_grid,
        ncp=ncp_grid,
        rhv=rhv_grid,
        min_ncp=min_ncp,
        min_rhv=min_rhv,
        min_refl=min_refl,
        max_refl=max_refl,
    )
    # 在体扫级排除掩码/无效速度，再取出布尔掩码供各 sweep 切片使用。
    volume_gatefilter.exclude_masked(velocity_grid)
    volume_gatefilter.exclude_invalid(velocity_grid)
    gfilter = _as_ray_gate_excluded(volume_gatefilter.gate_excluded)
    # DataArray 中的数值型填充哨兵（如 -9999）在 Py-ART 侧通常已落在 MaskedArray 中；
    # 此处在体扫级一并并入排除掩码，避免逐 sweep 重复处理。
    velocity_2d = np.asarray(velocity_grid.values[0, 0, 0, 0], dtype=np.float32)
    if gfilter.shape != velocity_2d.shape:
        raise ValueError(
            "gatefilter mask must match velocity ray/gate shape: "
            f"{gfilter.shape} vs {velocity_2d.shape}"
        )
    for key in ("_FillValue", "missing_value"):
        if key not in velocity_grid.attrs:
            continue
        try:
            fill_val = float(velocity_grid.attrs[key])
        except (TypeError, ValueError):
            continue
        if np.isfinite(fill_val):
            gfilter |= np.isclose(velocity_2d, fill_val, rtol=0.0, atol=0.0)

    for sweep_index, (sweep_slice, sweep_nyquist) in enumerate(
        zip(layout.sweep_slices, layout.nyquist_velocity)
    ):
        # 按体扫边界沿 ray 维截取当前 sweep；参考场未提供时保持 None。
        velocity_slice = velocity_grid.isel(lat=sweep_slice)
        ref_slice = (
            None
            if ref_velocity_grid is None
            else ref_velocity_grid.isel(lat=sweep_slice)
        )

        # 与 原方法 ``sfilter = gfilter[sweep_slice]`` 对齐：直接切片布尔掩码。
        sfilter = gfilter[sweep_slice]
        corrected_slice = _dealias_region_based_2d(
            velocity_slice=velocity_slice,
            gate_excluded=sfilter,
            nyquist_vel=float(sweep_nyquist),
            ref_velocity=ref_slice,
            interval_splits=interval_splits,
            interval_limits=interval_limits,
            skip_between_rays=skip_between_rays,
            skip_along_ray=skip_along_ray,
            centered=centered,
            rays_wrap_around=rays_wrap_around,
            keep_original=keep_original,
            sweep_index=sweep_index,
        )
        corrected_values[0, 0, 0, 0, sweep_slice, :] = corrected_slice

    # 将无效值重新回填为缺测标记，便于后续写出 NetCDF。
    valid_for_limits = np.ma.masked_invalid(corrected_values)
    output_values = np.array(corrected_values, dtype=np.float32, copy=True)
    invalid_mask = ~np.isfinite(output_values)
    if np.any(invalid_mask):
        output_values[invalid_mask] = fill_value

    corrected = _replace_polar_volume_values(
        velocity_grid,
        output_values,
    )
    corrected.name = data_name

    # Nyquist 速度属性如果在所有切片中一致，直接写成标量更简洁。
    if np.allclose(
        layout.nyquist_velocity,
        layout.nyquist_velocity[0],
    ):
        nyquist_attr: float | np.ndarray = float(layout.nyquist_velocity[0])
    else:
        nyquist_attr = np.array(
            layout.nyquist_velocity,
            dtype=np.float32,
            copy=True,
        )

    result_attrs = {
        "long_name": "dealiased velocity",
        "units": velocity_grid.attrs.get("units", ""),
        "nyquist_velocity": nyquist_attr,
        "_FillValue": fill_value,
    }
    if attrs is not None:
        result_attrs.update(attrs)
    if set_limits:
        _set_limits(
            valid_for_limits,
            layout.nyquist_velocity,
            result_attrs,
        )
    corrected.attrs.update(result_attrs)

    return corrected


__all__ = ["dealias_region_based", "RegionDealiasPlugin"]
