#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""region_dealias 算法命令行入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional, Sequence

import numpy as np
import xarray as xr


def process(
    velocity_path: str,
    *,
    ref_velocity_path: str = None,
    gatefilter: Literal[False] | None = False,
    gatefilter_path: str = None,
    refl_path: str = None,
    ncp_path: str = None,
    rhv_path: str = None,
    interval_splits: int = 3,
    interval_limits: Sequence[float] = None,
    skip_between_rays: int = 100,
    skip_along_ray: int = 100,
    centered: bool = True,
    nyquist_velocity: float = None,
    min_ncp: float = 0.5,
    min_rhv: float = None,
    min_refl: float = -20.0,
    max_refl: float = 100.0,
    rays_wrap_around: bool = None,
    keep_original: bool = False,
    set_limits: bool = True,
    data_name: str = "corrected_velocity",
    radar_lon: float = None,
    radar_lat: float = None,
    elevation_deg: float = 0.0,
    geo_resolution_deg: float = 0.01,
    geo_nlon: int = None,
    geo_nlat: int = None,
    auto_remap_to_latlon: bool = False,
    output_path: Optional[str] = None,
) -> xr.DataArray:
    """从文件路径执行基于区域连通关系的径向速度退模糊。

    读取六维网格 NetCDF / 可选掩码后，构造 ``RegionDealiasPlugin`` 并写出结果。
    门控三态与 Py-ART 对齐：``gatefilter_path`` 优先；否则 ``gatefilter=False``
    关闭自动过滤；``gatefilter=None`` 时按 ``refl/ncp/rhv`` 做 moment 过滤
    （缺字段则跳过对应规则，不报错）。

    参数
    ----
    velocity_path : str
        待退模糊速度场 NetCDF 路径。
    ref_velocity_path : str, optional
        参考速度场路径，用于区域合并后的结果锚定。
    gatefilter : False or None, optional
        ``False``（默认）关闭自动过滤；``None`` 启用 moment 自动过滤。
        若同时提供 ``gatefilter_path``，以掩码为准。
    gatefilter_path : str, optional
        布尔掩码 ``.npy`` 路径，读取后构造显式 ``GridGateFilter``。
    refl_path, ncp_path, rhv_path : str, optional
        moment 自动过滤所用反射率 / NCP / RhoHV 场路径。
    interval_splits : int, optional
        Nyquist 区间初始分段数；``interval_limits`` 非空时不使用。
    interval_limits : sequence of float, optional
        自定义速度分段边界。
    skip_between_rays, skip_along_ray : int, optional
        跨射线 / 沿径向连接区域时允许跨越的最大过滤间隔。
    centered : bool, optional
        是否将整体展开圈数居中到 0 附近。
    nyquist_velocity : float, optional
        显式 Nyquist 速度；为空时从速度场属性读取。
    min_ncp, min_rhv, min_refl, max_refl : float, optional
        moment 自动过滤阈值；对应字段缺失时跳过。
    rays_wrap_around : bool, optional
        是否将方位向首尾视为相邻；``None`` 时按 ``scan_type`` 推断。
    keep_original : bool, optional
        被过滤格点是否保留原始速度；``False`` 时输出缺测。
    set_limits : bool, optional
        是否写入输出 ``valid_min`` / ``valid_max``。
    data_name : str, optional
        输出 DataArray 名称。
    radar_lon, radar_lat : float, optional
        雷达站点经纬度（地理后处理 / 重映射用）。
    elevation_deg : float, optional
        仰角（度）。
    geo_resolution_deg : float, optional
        自动规则经纬网格分辨率（度）。
    geo_nlon, geo_nlat : int, optional
        自动规则经纬网格格点数。
    auto_remap_to_latlon : bool, optional
        是否将结果重映射到规则经纬网格。
    output_path : str, optional
        输出 NetCDF 路径；为空则只返回内存结果。

    返回
    ----
    xr.DataArray
        退模糊后的速度场（``float32``）；若开启重映射则为规则经纬网格。
    """
    from radar_wind_dealiasing.cli import (
        _read_griddata,
        _read_npy_array,
        _write_griddata_to_nc,
    )
    from radar_wind_dealiasing.src import GridGateFilter
    from radar_wind_dealiasing.src.region_dealias import RegionDealiasPlugin

    velocity = _read_griddata(velocity_path)
    ref_velocity = (
        _read_griddata(ref_velocity_path) if ref_velocity_path is not None else None
    )
    refl = _read_griddata(refl_path) if refl_path is not None else None
    ncp = _read_griddata(ncp_path) if ncp_path is not None else None
    rhv = _read_griddata(rhv_path) if rhv_path is not None else None

    # 与 Py-ART 三态对齐（路径优先，便于默认 gatefilter=False 时仍可传掩码）：
    # - 掩码路径：显式 GridGateFilter
    # - False：关闭自动过滤
    # - None：moment 自动过滤（缺 refl/ncp/rhv 也不报错）
    if gatefilter_path is not None:
        gatefilter_arg = GridGateFilter.from_mask(
            velocity,
            np.asarray(_read_npy_array(gatefilter_path), dtype=bool),
        )
    elif gatefilter is False:
        gatefilter_arg = False
    else:
        gatefilter_arg = None

    plugin = RegionDealiasPlugin(
        interval_splits=interval_splits,
        interval_limits=interval_limits,
        skip_between_rays=skip_between_rays,
        skip_along_ray=skip_along_ray,
        centered=centered,
        nyquist_velocity=nyquist_velocity,
        gatefilter=gatefilter_arg,
        min_ncp=min_ncp,
        min_rhv=min_rhv,
        min_refl=min_refl,
        max_refl=max_refl,
        rays_wrap_around=rays_wrap_around,
        keep_original=keep_original,
        set_limits=set_limits,
        data_name=data_name,
        radar_lon=radar_lon,
        radar_lat=radar_lat,
        elevation_deg=elevation_deg,
        geo_resolution_deg=geo_resolution_deg,
        geo_nlon=geo_nlon,
        geo_nlat=geo_nlat,
        auto_remap_to_latlon=auto_remap_to_latlon,
    )

    result = plugin.process(
        velocity=velocity,
        ref_velocity=ref_velocity,
        refl=refl,
        ncp=ncp,
        rhv=rhv,
    )

    if (
        not np.issubdtype(result.values.dtype, np.floating)
        or result.values.dtype != np.float32
    ):
        result = result.astype(np.float32, copy=False)

    if output_path is not None:
        _write_griddata_to_nc(result, output_path)

    return result


if __name__ == "__main__":
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from radar_wind_dealiasing.cli.region_dealias import process

    # 测试数据路径：仅使用单层仰角样例，避免大体扫文件进入仓库
    base_dir = Path(__file__).resolve().parents[1] / "test_data" / "region_dealias"
    data_dir = base_dir / "cli_input"
    velocity_path = str(data_dir / "velocity_sweep0.nc")
    gatefilter_path = str(data_dir / "grid_gatefilter_mask_sweep0.npy")
    output_path = str(base_dir / "cli_output" / "region_dealias_cli.nc")

    process(
        velocity_path,
        gatefilter_path=gatefilter_path,
        data_name="corrected_velocity_cli",
        output_path=output_path,
    )
