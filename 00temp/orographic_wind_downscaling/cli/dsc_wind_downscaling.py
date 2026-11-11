#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形风速降尺度命令行。

在本包目录执行::

    python cli/dsc_wind_downscaling.py --wind-speed-path PATH --sigma-path PATH --target-orography-path PATH --standard-orography-path PATH --silhouette-roughness-path PATH --model-resolution 1500
    python -m cli.dsc_wind_downscaling --wind-speed-path PATH --sigma-path PATH --target-orography-path PATH --standard-orography-path PATH --silhouette-roughness-path PATH --model-resolution 1500

Python::

    from cli.dsc_wind_downscaling import DscWindDownscalingCli
    DscWindDownscalingCli.call(wind_speed_path="PATH", sigma_path="PATH", target_orography_path="PATH", standard_orography_path="PATH", silhouette_roughness_path="PATH", model_resolution=1500)
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import xarray as xr
import meteva_base as meb


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

def process(
    wind_speed_path: str,
    sigma_path: str,
    target_orography_path: str,
    standard_orography_path: str,
    silhouette_roughness_path: str,
    model_resolution: float,
    vegetative_roughness_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    output_height_level: Optional[float] = None,
    output_height_level_units: str = "m",
    absolute_correction_tol: Optional[float] = None,
    href_scale: Optional[float] = None,
    dx_max_factor: Optional[float] = None,
    dx_min_factor: Optional[float] = None,
    config=None,
) -> xr.DataArray:
    """风速降尺度处理流程。

    参数
    ----------
    wind_speed_path : str
        待订正风速场 nc 文件路径。
    sigma_path : str
        网格高度标准差场 nc 文件路径。
    target_orography_path : str
        目标网格地形高度场 nc 文件路径。
    standard_orography_path : str
        标准网格地形高度场 nc 文件路径。
    silhouette_roughness_path : str
        地形轮廓粗糙度场 nc 文件路径。
    model_resolution : float
        原始模式分辨率（米）。
    vegetative_roughness_path : str, optional
        植被粗糙度长度场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    output_height_level : float, optional
        若指定，则从结果中提取该高度层。
    output_height_level_units : str, default="m"
        ``output_height_level`` 的单位。
    absolute_correction_tol, href_scale, dx_max_factor, dx_min_factor : float, optional
        原方法内硬编码常数的外置；省略时用模块默认（与 IMPROVER 一致）。
        HC 偏大时优先试增大 ``dx_max_factor``；RC 偏强时再调 ``absolute_correction_tol`` / ``href_scale``。

    返回
    -------
    xr.DataArray
        订正后的风速场。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "vegetative_roughness_path": (vegetative_roughness_path, "str"),
        "output_path": (output_path, "str"),
        "output_height_level": (output_height_level, "float"),
        "absolute_correction_tol": (absolute_correction_tol, "float"),
        "href_scale": (href_scale, "float"),
        "dx_max_factor": (dx_max_factor, "float"),
        "dx_min_factor": (dx_min_factor, "float"),
    })
    vegetative_roughness_path = _over['vegetative_roughness_path']
    output_path = _over['output_path']
    output_height_level = _over['output_height_level']
    absolute_correction_tol = _over['absolute_correction_tol']
    href_scale = _over['href_scale']
    dx_max_factor = _over['dx_max_factor']
    dx_min_factor = _over['dx_min_factor']
    from orographic_wind_downscaling.src.wind_downscaling import (
        RoughnessCorrection,
        ABSOLUTE_CORRECTION_TOL,
        HREF_SCALE,
        DX_MAX_FACTOR,
        DX_MIN_FACTOR,
    )

    _unbounded = (-np.inf, np.inf, np.nan)

    if output_height_level_units and output_height_level is None:
        warnings.warn(
            "output_height_level_units 已设置，但未提供 output_height_level；该参数不会生效。"
        )

    wind_speed = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_speed_path), valid_val=_unbounded
    )
    sigma = meb.checkout_griddata(
        meb.read_griddata_from_nc(sigma_path), is_single=True, valid_val=_unbounded
    )
    target_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(target_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    standard_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(standard_orography_path),
        is_single=True,
        valid_val=_unbounded,
    )
    silhouette_roughness = meb.checkout_griddata(
        meb.read_griddata_from_nc(silhouette_roughness_path), is_single=True
    )
    vegetative_roughness = (
        None
        if vegetative_roughness_path is None
        else meb.checkout_griddata(
            meb.read_griddata_from_nc(vegetative_roughness_path), is_single=True
        )
    )

    plugin = RoughnessCorrection(
        silhouette_roughness,
        sigma,
        target_orography,
        standard_orography,
        model_resolution,
        z0=vegetative_roughness,
        absolute_correction_tol=(
            ABSOLUTE_CORRECTION_TOL
            if absolute_correction_tol is None
            else float(absolute_correction_tol)
        ),
        href_scale=HREF_SCALE if href_scale is None else float(href_scale),
        dx_max_factor=DX_MAX_FACTOR if dx_max_factor is None else float(dx_max_factor),
        dx_min_factor=DX_MIN_FACTOR if dx_min_factor is None else float(dx_min_factor),
    )
    result, _hc_add = plugin.process(wind_speed)

    result = result.astype(np.float32, copy=False)
    result.name = wind_speed.name or result.name or "wind_speed"

    if output_height_level is not None:
        result = _extract_height_level(
            result,
            output_height_level=output_height_level,
            output_height_level_units=output_height_level_units,
        )

    if output_path is not None:
        _write_result_netcdf_float32(result, output_path)

    return result


def _extract_height_level(
    data: xr.DataArray,
    output_height_level: float,
    output_height_level_units: str,
) -> xr.DataArray:
    """按指定高度提取单层结果。"""
    level_name = "level"
    if level_name not in data.coords:
        raise ValueError("结果中不存在 level 坐标。")

    levels = np.asarray(data.coords[level_name].values, dtype=np.float64)
    coord_units = data.coords[level_name].attrs.get("units", "m")
    target_level = float(output_height_level)

    if output_height_level_units and output_height_level_units != coord_units:
        from cf_units import Unit

        target_level = float(
            Unit(output_height_level_units).convert(target_level, Unit(coord_units))
        )

    idx = np.where(np.isclose(levels, target_level, rtol=0.0, atol=1e-6))[0]
    if idx.size == 0:
        raise ValueError(
            "Requested height level not found. "
            f"Available levels: {levels.tolist()} (units: {coord_units})"
        )
    return data.isel({level_name: int(idx[0])})


def _write_result_netcdf_float32(data: xr.DataArray, output_path: str) -> None:
    """以 float32 直写 NetCDF，避免 scale_factor 量化误差。"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    output = data.astype(np.float32, copy=False)
    var_name = output.name or "wind_speed"
    output.name = var_name
    dataset = output.to_dataset(name=var_name)
    dataset.to_netcdf(
        target,
        engine="netcdf4",
        encoding={
            var_name: {
                "dtype": "float32",
                "zlib": False,
                "_FillValue": np.float32(np.nan),
            }
        },
    )


class DscWindDownscalingCli(CliBase):
    """``dsc_wind_downscaling`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_wind_downscaling.py"
    description = (
        "地形风速降尺度。\n"
        "输入路径与模式分辨率必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_wind_downscaling.py --help\n"
        "  python cli/dsc_wind_downscaling.py --wind-speed-path PATH --sigma-path PATH "
        "--target-orography-path PATH --standard-orography-path PATH "
        "--silhouette-roughness-path PATH --model-resolution 1500 --output-path OUT.nc\n"
        "  python -m cli.dsc_wind_downscaling --wind-speed-path PATH --sigma-path PATH "
        "--target-orography-path PATH --standard-orography-path PATH "
        "--silhouette-roughness-path PATH --model-resolution 1500 --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--wind-speed-path", required=True, metavar="PATH", help="待订正风速场 NetCDF。必填。")
        parser.add_argument("--sigma-path", required=True, metavar="PATH", help="网格高度标准差场 NetCDF。必填。")
        parser.add_argument("--target-orography-path", required=True, metavar="PATH", help="目标网格地形高度场 NetCDF。必填。")
        parser.add_argument("--standard-orography-path", required=True, metavar="PATH", help="标准网格地形高度场 NetCDF。必填。")
        parser.add_argument("--silhouette-roughness-path", required=True, metavar="PATH", help="地形轮廓粗糙度场 NetCDF。必填。")
        parser.add_argument("--model-resolution", required=True, type=float, help="原始模式分辨率（米）。必填。")
        parser.add_argument("--vegetative-roughness-path", default=None, metavar="PATH", help="植被粗糙度长度场 NetCDF。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument("--output-height-level", dest="output_height_level", type=float, default=None, help="若指定，则从结果中提取该高度层。")
        parser.add_argument("--output-height-level-units", dest="output_height_level_units", default=None, help="output_height_level 的单位。省略则用 m。")
        parser.add_argument(
            "--absolute-correction-tol",
            dest="absolute_correction_tol",
            type=float,
            default=None,
            help="扰动衰减阈值 ε，默认 0.04。",
        )
        parser.add_argument(
            "--href-scale",
            dest="href_scale",
            type=float,
            default=None,
            help="参考高度相对半峰谷高度上限倍数，默认 2.0。",
        )
        parser.add_argument(
            "--dx-max-factor",
            dest="dx_max_factor",
            type=float,
            default=None,
            help="dx_max = factor * modres，默认 3.0。",
        )
        parser.add_argument(
            "--dx-min-factor",
            dest="dx_min_factor",
            type=float,
            default=None,
            help="dx_min = factor * ppres，默认 0.5。",
        )
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_wind_downscaling_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_wind_downscaling`` 都进这里。"""
    return DscWindDownscalingCli().main(argv)


main = dsc_wind_downscaling_cli


if __name__ == "__main__":
    raise SystemExit(dsc_wind_downscaling_cli())
