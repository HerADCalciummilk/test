#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""直接用 U/V 计算地形增强的命令行。

输入须已是边界层代表高度上的单层场。温度、湿度、气压、U、V
由 ``OrographicEnhancement`` 重采样到传入的地形网格。
本入口不解析风速风向，也不做风矢量旋转。

在本包目录执行::

    python cli/dsc_orographic_enhancement_uv.py --temperature-path PATH --humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH --orography-path PATH
    python -m cli.dsc_orographic_enhancement_uv --temperature-path PATH --humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH --orography-path PATH

Python::

    from cli.dsc_orographic_enhancement_uv import DscOrographicEnhancementUvCli
    DscOrographicEnhancementUvCli.call(temperature_path="PATH", humidity_path="PATH", pressure_path="PATH", uwind_path="PATH", vwind_path="PATH", orography_path="PATH")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
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


def process(
    temperature_path: str,
    humidity_path: str,
    pressure_path: str,
    uwind_path: str,
    vwind_path: str,
    orography_path: str,
    output_path: Optional[str] = None,
    *,
    config=None,
) -> xr.DataArray:
    """用已有 U/V 计算地形增强。

    参数
    ----------
    temperature_path : str
        温度输入场 nc 文件路径。
    humidity_path : str
        相对湿度输入场 nc 文件路径。
    pressure_path : str
        气压输入场 nc 文件路径。
    uwind_path : str
        东西风分量 nc 文件路径。
    vwind_path : str
        南北风分量 nc 文件路径。
    orography_path : str
        目标地形网格场 nc 文件路径。增强场落在这张网格上。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    config : str, optional
        运行配置 ini。省略则用包内 ``resource/conf.ini``。

    返回
    -------
    xr.DataArray
        地形增强结果，单位 ``m s-1``。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(
        __file__,
        config,
        {
            "output_path": (output_path, "str"),
        },
    )
    output_path = _over["output_path"]
    from orographic_precipitation_downscaling.src.orographic_enhancement import (
        OrographicEnhancement,
    )

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
    uwind = meb.checkout_griddata(
        meb.read_griddata_from_nc(uwind_path), valid_val=_unbounded
    )
    vwind = meb.checkout_griddata(
        meb.read_griddata_from_nc(vwind_path), valid_val=_unbounded
    )
    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=_unbounded,
    )

    for label, field in (
        ("相对湿度场", humidity),
        ("气压场", pressure),
        ("东西风场", uwind),
        ("南北风场", vwind),
    ):
        if not meb.checkout_griddata_same_coords([temperature, field], is_time_match=True):
            raise ValueError(f"{label}与温度场的空间/时效坐标不一致")

    result = OrographicEnhancement()(
        temperature,
        humidity,
        pressure,
        uwind,
        vwind,
        orography,
    )

    if output_path is not None:
        # meb.write_griddata_to_nc 对 ~1e-6 m/s 量级结果会量化成 0，改用 xarray 直写。
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "orographic_enhancement"
        result.to_dataset(name=var_name).to_netcdf(output_file, mode="w")

    return result


class DscOrographicEnhancementUvCli(CliBase):
    """``dsc_orographic_enhancement_uv`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_orographic_enhancement_uv.py"
    description = (
        "用已有 U/V 计算地形降水增强。\n"
        "六个输入路径必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_orographic_enhancement_uv.py --help\n"
        "  python cli/dsc_orographic_enhancement_uv.py --temperature-path PATH --humidity-path PATH "
        "--pressure-path PATH --uwind-path PATH --vwind-path PATH "
        "--orography-path PATH --output-path OUT.nc\n"
        "  python -m cli.dsc_orographic_enhancement_uv --temperature-path PATH --humidity-path PATH "
        "--pressure-path PATH --uwind-path PATH --vwind-path PATH "
        "--orography-path PATH --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--temperature-path", required=True, metavar="PATH", help="温度场 NetCDF。必填。")
        parser.add_argument("--humidity-path", required=True, metavar="PATH", help="相对湿度场 NetCDF。必填。")
        parser.add_argument("--pressure-path", required=True, metavar="PATH", help="气压场 NetCDF。必填。")
        parser.add_argument("--uwind-path", required=True, metavar="PATH", help="东西风分量 NetCDF。必填。")
        parser.add_argument("--vwind-path", required=True, metavar="PATH", help="南北风分量 NetCDF。必填。")
        parser.add_argument("--orography-path", required=True, metavar="PATH", help="目标地形网格 NetCDF。必填。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 NetCDF。省略则不写文件。")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_orographic_enhancement_uv_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_orographic_enhancement_uv`` 都进这里。"""
    return DscOrographicEnhancementUvCli().main(argv)


main = dsc_orographic_enhancement_uv_cli


if __name__ == "__main__":
    raise SystemExit(dsc_orographic_enhancement_uv_cli())
