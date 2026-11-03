#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""径向速度区域退模糊命令行。

在本包目录执行::

    python cli/region_dealias.py --velocity-path PATH [--output-path PATH]
    python -m cli.region_dealias --velocity-path PATH

Python::

    from cli.region_dealias import RegionDealiasCli
    RegionDealiasCli.call(velocity_path="PATH")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal, Optional, Sequence

import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    """沿用原脚本：把 00temp 放进 sys.path，并让包根上的 utils 优先。"""
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.conf_ini import overlay_none


def _csv_floats(text: str):
    parts = [item.strip() for item in str(text).split(",") if item.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要逗号分隔的数值")
    return [float(item) for item in parts]


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
    output_path: Optional[str] = None, config=None) -> xr.DataArray:
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
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "ref_velocity_path": (ref_velocity_path, "str"),
        "gatefilter_path": (gatefilter_path, "str"),
        "refl_path": (refl_path, "str"),
        "ncp_path": (ncp_path, "str"),
        "rhv_path": (rhv_path, "str"),
        "interval_limits": (interval_limits, "float_list"),
        "nyquist_velocity": (nyquist_velocity, "float"),
        "min_rhv": (min_rhv, "float"),
        "rays_wrap_around": (rays_wrap_around, "bool"),
        "radar_lon": (radar_lon, "float"),
        "radar_lat": (radar_lat, "float"),
        "geo_nlon": (geo_nlon, "int"),
        "geo_nlat": (geo_nlat, "int"),
        "output_path": (output_path, "str"),
    })
    ref_velocity_path = _over['ref_velocity_path']
    gatefilter_path = _over['gatefilter_path']
    refl_path = _over['refl_path']
    ncp_path = _over['ncp_path']
    rhv_path = _over['rhv_path']
    interval_limits = _over['interval_limits']
    nyquist_velocity = _over['nyquist_velocity']
    min_rhv = _over['min_rhv']
    rays_wrap_around = _over['rays_wrap_around']
    radar_lon = _over['radar_lon']
    radar_lat = _over['radar_lat']
    geo_nlon = _over['geo_nlon']
    geo_nlat = _over['geo_nlat']
    output_path = _over['output_path']
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


class RegionDealiasCli(CliBase):
    """``region_dealias`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/region_dealias.py"
    description = (
        "基于区域连通关系的径向速度退模糊。\n"
        "必填路径由命令行传入。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。\n"
        "--gatefilter false 关闭自动过滤；none 启用 moment 自动过滤。"
        "提供 --gatefilter-path 时以掩码为准。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/region_dealias.py --help\n"
        "  python cli/region_dealias.py --velocity-path PATH --output-path OUT.nc\n"
        "  python -m cli.region_dealias --velocity-path PATH --gatefilter none --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--velocity-path", required=True, metavar="PATH", help="待退模糊速度场 NetCDF。必填。")
        parser.add_argument("--ref-velocity-path", default=None, metavar="PATH", help="参考速度场。")
        parser.add_argument("--gatefilter", default=None, choices=("false", "none"), help="false 关闭自动过滤（默认）；none 启用 moment 自动过滤。")
        parser.add_argument("--gatefilter-path", default=None, metavar="PATH", help="布尔掩码 .npy。优先于 --gatefilter。")
        parser.add_argument("--refl-path", default=None, metavar="PATH", help="moment 过滤用反射率。")
        parser.add_argument("--ncp-path", default=None, metavar="PATH", help="moment 过滤用 NCP。")
        parser.add_argument("--rhv-path", default=None, metavar="PATH", help="moment 过滤用 RhoHV。")
        parser.add_argument("--interval-splits", dest="interval_splits", type=int, default=None, help="Nyquist 区间初始分段数。省略则用 3。")
        parser.add_argument("--interval-limits", dest="interval_limits", type=_csv_floats, default=None, help="自定义速度分段边界，逗号分隔。")
        parser.add_argument("--skip-between-rays", dest="skip_between_rays", type=int, default=None, help="跨射线最大过滤间隔。省略则用 100。")
        parser.add_argument("--skip-along-ray", dest="skip_along_ray", type=int, default=None, help="沿径向最大过滤间隔。省略则用 100。")
        self.add_optional_bool(parser, "--centered", help_true="展开圈数居中到 0 附近。", help_false="不居中展开圈数。省略则用函数默认值 true。")
        parser.add_argument("--nyquist-velocity", dest="nyquist_velocity", type=float, default=None, help="显式 Nyquist 速度。省略则从速度场属性读取。")
        parser.add_argument("--min-ncp", dest="min_ncp", type=float, default=None, help="NCP 下限。省略则用 0.5。")
        parser.add_argument("--min-rhv", dest="min_rhv", type=float, default=None, help="RhoHV 下限。")
        parser.add_argument("--min-refl", dest="min_refl", type=float, default=None, help="反射率下限。省略则用 -20。")
        parser.add_argument("--max-refl", dest="max_refl", type=float, default=None, help="反射率上限。省略则用 100。")
        self.add_optional_bool(parser, "--rays-wrap-around", help_true="方位向首尾视为相邻。", help_false="方位向首尾不视为相邻。省略则按 scan_type 推断。")
        self.add_optional_bool(parser, "--keep-original", help_true="被过滤格点保留原始速度。", help_false="被过滤格点输出缺测。省略则用函数默认值 false。")
        self.add_optional_bool(parser, "--set-limits", help_true="写入 valid_min/valid_max。", help_false="不写 valid_min/valid_max。省略则用函数默认值 true。")
        parser.add_argument("--data-name", default=None, help="输出 DataArray 名称。省略则用 corrected_velocity。")
        parser.add_argument("--radar-lon", dest="radar_lon", type=float, default=None, help="雷达经度。")
        parser.add_argument("--radar-lat", dest="radar_lat", type=float, default=None, help="雷达纬度。")
        parser.add_argument("--elevation-deg", dest="elevation_deg", type=float, default=None, help="仰角（度）。省略则用 0。")
        parser.add_argument("--geo-resolution-deg", dest="geo_resolution_deg", type=float, default=None, help="规则经纬网格分辨率（度）。省略则用 0.01。")
        parser.add_argument("--geo-nlon", dest="geo_nlon", type=int, default=None, help="规则经纬网格经向格点数。")
        parser.add_argument("--geo-nlat", dest="geo_nlat", type=int, default=None, help="规则经纬网格纬向格点数。")
        self.add_optional_bool(parser, "--auto-remap-to-latlon", help_true="重映射到规则经纬网格。", help_false="不重映射。省略则用函数默认值 false。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则只返回内存结果。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        gatefilter = params.pop("gatefilter", None)
        kwargs = {key: value for key, value in params.items() if value is not None}
        if gatefilter == "false":
            kwargs["gatefilter"] = False
        elif gatefilter == "none":
            kwargs["gatefilter"] = None
        process(**kwargs)
        return 0


def region_dealias_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.region_dealias`` 都进这里。"""
    return RegionDealiasCli().main(argv)


main = region_dealias_cli


if __name__ == "__main__":
    raise SystemExit(region_dealias_cli())
