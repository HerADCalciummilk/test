#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""地形降水增强命令行。

在本包目录执行::

    python cli/dsc_orographic_enhancement.py --temperature-path PATH --humidity-path PATH --pressure-path PATH --wind-speed-path PATH --wind-direction-path PATH --orography-path PATH
    python -m cli.dsc_orographic_enhancement --temperature-path PATH --humidity-path PATH --pressure-path PATH --wind-speed-path PATH --wind-direction-path PATH --orography-path PATH

Python::

    from cli.dsc_orographic_enhancement import DscOrographicEnhancementCli
    DscOrographicEnhancementCli.call(temperature_path="PATH", humidity_path="PATH", pressure_path="PATH", wind_speed_path="PATH", wind_direction_path="PATH", orography_path="PATH")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import xarray as xr
import meteva_base as meb
import numpy as np


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
    temperature_path: str,
    humidity_path: str,
    pressure_path: str,
    wind_speed_path: str,
    wind_direction_path: str,
    orography_path: str,
    output_path: Optional[str] = None,
    *,
    boundary_height: float = 1000.0,
    boundary_height_units: str = "m", config=None) -> xr.DataArray:
    """地形增强处理流程。

    参数
    ----------
    temperature_path : str
        温度输入场 nc 文件路径。
    humidity_path : str
        相对湿度输入场 nc 文件路径。
    pressure_path : str
        气压输入场 nc 文件路径。
    wind_speed_path : str
        风速输入场 nc 文件路径。
    wind_direction_path : str
        风向输入场 nc 文件路径（相对真北角度）。
    orography_path : str
        目标地形网格场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    boundary_height : float, default=1000.0
        边界层代表高度。
    boundary_height_units : str, default="m"
        边界层代表高度单位。

    返回
    -------
    xr.DataArray
        地形增强结果，单位 ``m s-1``。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "output_path": (output_path, "str"),
    })
    output_path = _over['output_path']
    from orographic_precipitation_downscaling.src.orographic_enhancement import MetaOrographicEnhancement
    
    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )
    humidity = meb.checkout_griddata(
        meb.read_griddata_from_nc(humidity_path), valid_val=_unbounded
    )
    pressure = meb.checkout_griddata(
        meb.read_griddata_from_nc(pressure_path), valid_val=_unbounded
    )
    wind_speed = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_speed_path), valid_val=_unbounded
    )
    wind_direction = meb.checkout_griddata(
        meb.read_griddata_from_nc(wind_direction_path), valid_val=_unbounded
    )
    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=_unbounded,
    )

    for label, field in (
        ("相对湿度场", humidity),
        ("气压场", pressure),
        ("风速场", wind_speed),
        ("风向场", wind_direction),
    ):
        if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    plugin = MetaOrographicEnhancement(
        boundary_height=boundary_height,
        boundary_height_units=boundary_height_units,
    )
    result = plugin(
        temperature,
        humidity,
        pressure,
        wind_speed,
        wind_direction,
        orography,
    )

    if output_path is not None:
        # meb.write_griddata_to_nc 对 ~1e-6 m/s 量级结果会量化成 0，改用 xarray 直写。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "orographic_enhancement"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")

    return result


class DscOrographicEnhancementCli(CliBase):
    """``dsc_orographic_enhancement`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_orographic_enhancement.py"
    description = (
        "地形降水增强。\n"
        "六个输入路径必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_orographic_enhancement.py --help\n"
        "  python cli/dsc_orographic_enhancement.py --temperature-path PATH --humidity-path PATH "
        "--pressure-path PATH --wind-speed-path PATH --wind-direction-path PATH "
        "--orography-path PATH --output-path OUT.nc\n"
        "  python -m cli.dsc_orographic_enhancement --temperature-path PATH --humidity-path PATH "
        "--pressure-path PATH --wind-speed-path PATH --wind-direction-path PATH "
        "--orography-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--temperature-path", required=True, metavar="PATH", help="温度场 NetCDF。必填。")
        parser.add_argument("--humidity-path", required=True, metavar="PATH", help="相对湿度场 NetCDF。必填。")
        parser.add_argument("--pressure-path", required=True, metavar="PATH", help="气压场 NetCDF。必填。")
        parser.add_argument("--wind-speed-path", required=True, metavar="PATH", help="风速场 NetCDF。必填。")
        parser.add_argument("--wind-direction-path", required=True, metavar="PATH", help="风向场 NetCDF（相对真北角度）。必填。")
        parser.add_argument("--orography-path", required=True, metavar="PATH", help="目标地形网格 NetCDF。必填。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument("--boundary-height", dest="boundary_height", type=float, default=None, help="边界层代表高度。省略则用 1000。")
        parser.add_argument("--boundary-height-units", dest="boundary_height_units", default=None, help="边界层高度单位。省略则用 m。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_orographic_enhancement_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_orographic_enhancement`` 都进这里。"""
    return DscOrographicEnhancementCli().main(argv)


main = dsc_orographic_enhancement_cli


if __name__ == "__main__":
    raise SystemExit(dsc_orographic_enhancement_cli())
