#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""计算层结递减率的命令行。

在本包目录执行::

    python -m cli lapse-rate --temperature-path PATH
    python cli/dsc_temp_lapse_rate.py --temperature-path PATH

Python::

    from cli.dsc_temp_lapse_rate import DscTempLapseRateCli
    DscTempLapseRateCli.call(temperature_path="PATH", dry_adiabatic=True)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    root_s = str(root)
    parent_s = str(parent)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if parent_s not in sys.path:
        sys.path.append(parent_s)


_bootstrap_paths()

import numpy as np
import xarray as xr
import meteva_base as meb

from utils.cli_base import CliBase

DALR = -0.0098  # # 干绝热递减率


def _as_lapse_rate_dataarray(
    values: np.ndarray,
    template: xr.DataArray,
    name: str = "air_temperature_lapse_rate",
    units: str = "K m-1",
) -> xr.DataArray:
    """用模板网格将结果数组封装为 DataArray。"""
    result = xr.DataArray(
        values.astype(np.float32, copy=False),
        dims=template.dims,
        coords=template.coords,
        attrs=dict(template.attrs),
        name=name,
    )
    result.attrs["units"] = units
    return result


def process(
    temperature_path: str,
    orography_path: Optional[str] = None,
    land_sea_mask_path: Optional[str] = None,
    output_path: Optional[str] = None,
    *,
    max_height_diff: float = 35.0,
    nbhood_radius: int = 7,
    max_lapse_rate: float = -3 * DALR,
    min_lapse_rate: float = DALR,
    dry_adiabatic: bool = False, config=None) -> xr.DataArray:
    """计算温度层结递减率（K m-1）。

    参数
    ----------
    temperature_path : str
        气温输入场 nc 文件路径。
    orography_path : str, optional
        地形高度场 nc 文件路径，单位通常为 m。
    land_sea_mask_path : str, optional
        海陆掩码 nc 文件路径，陆地为真值，海洋为假值。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件。
    max_height_diff : float, default=35.0
        计算邻域回归时允许的最大高度差（m）。
    nbhood_radius : int, default=7
        邻域半径（格点数）。
    max_lapse_rate : float, default=-3*DALR
        层结递减率上限（K m-1）。
    min_lapse_rate : float, default=DALR
        层结递减率下限（K m-1）。
    dry_adiabatic : bool, default=False
        若为真，直接返回干绝热递减率场，不执行真实递减率估计。

    返回
    -------
    xr.DataArray
        层结递减率场，单位 ``K m-1``。
    """
    from orographic_temperature_downscaling.src.lapse_rate import LapseRate
        
    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.checkout_griddata(
        meb.read_griddata_from_nc(temperature_path), valid_val=_unbounded
    )

    if dry_adiabatic:
        result = np.full_like(
            np.asarray(temperature.values, dtype=np.float32), DALR, dtype=np.float32
        )
        result = _as_lapse_rate_dataarray(result, temperature)
    else:
        if min_lapse_rate > max_lapse_rate:
            raise ValueError("最小层结递减率不能大于最大层结递减率。")
        if max_height_diff < 0:
            raise ValueError("max_height_diff 必须大于等于 0。")
        if nbhood_radius < 0:
            raise ValueError("nbhood_radius 必须大于等于 0。")

        if orography_path is None or land_sea_mask_path is None:
            raise RuntimeError("计算真实层结递减率时，必须同时提供 orography_path 和 land_sea_mask_path。")

        orography = meb.checkout_griddata(
            meb.read_griddata_from_nc(orography_path), valid_val=_unbounded
        )
        land_sea_mask = meb.checkout_griddata(meb.read_griddata_from_nc(land_sea_mask_path))

        if not meb.checkout_griddata_same_coords([temperature, orography], is_time_match=False):
            raise ValueError("地形高度场与温度场的坐标不一致")
        if not meb.checkout_griddata_same_coords([temperature, land_sea_mask], is_time_match=True):
            raise ValueError("海陆掩码与温度场的空间/时效坐标不一致")

        plugin = LapseRate(
            max_height_diff=max_height_diff,
            nbhood_radius=nbhood_radius,
            max_lapse_rate=max_lapse_rate,
            min_lapse_rate=min_lapse_rate,
        )
        result = plugin(temperature, orography, land_sea_mask)
        if isinstance(result, xr.DataArray):
            result = result.copy()
            result.name = "air_temperature_lapse_rate"
            result.attrs["units"] = "K m-1"
        else:
            result = _as_lapse_rate_dataarray(result, temperature)

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)

    return result


def _omit_none(kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


_CONFIG_HELP = (
    "运行配置文件，传给 process 的 config。"
    "省略则为 None，process 使用各参数自身的默认值。"
)


class DscTempLapseRateCli(CliBase):
    """计算温度层结递减率。``run`` 调用 ``process``。"""

    prog = "python cli/dsc_temp_lapse_rate.py"
    description = (
        "计算温度层结递减率（K m-1）。\n"
        "未在命令行给出的可选项保持 process 的默认值。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli lapse-rate --help\n"
        "  python -m cli lapse-rate --temperature-path PATH --orography-path PATH "
        "--land-sea-mask-path PATH --output-path PATH\n"
        "  python cli/dsc_temp_lapse_rate.py --temperature-path PATH --dry-adiabatic\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--temperature-path", required=True, metavar="PATH", help="气温输入场 nc。")
        parser.add_argument("--orography-path", default=None, metavar="PATH", help="地形高度场 nc。省略则为 None。")
        parser.add_argument("--land-sea-mask-path", default=None, metavar="PATH", help="海陆掩码 nc。省略则为 None。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 nc。省略则不写文件。")
        parser.add_argument(
            "--max-height-diff",
            type=float,
            default=None,
            help="邻域回归允许的最大高度差（m）。省略则使用 process 默认值 35。",
        )
        parser.add_argument(
            "--nbhood-radius",
            type=int,
            default=None,
            help="邻域半径（格点数）。省略则使用 process 默认值 7。",
        )
        parser.add_argument(
            "--max-lapse-rate",
            type=float,
            default=None,
            help="层结递减率上限（K m-1）。省略则使用 process 默认值 -3*DALR。",
        )
        parser.add_argument(
            "--min-lapse-rate",
            type=float,
            default=None,
            help="层结递减率下限（K m-1）。省略则使用 process 默认值 DALR。",
        )
        CliBase.add_optional_bool(
            parser,
            "--dry-adiabatic",
            help_true="直接返回干绝热递减率场。",
            help_false="按地形和海陆掩码估计真实递减率。省略则使用 process 默认值。",
        )
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        temperature_path,
        orography_path=None,
        land_sea_mask_path=None,
        output_path=None,
        max_height_diff=None,
        nbhood_radius=None,
        max_lapse_rate=None,
        min_lapse_rate=None,
        dry_adiabatic=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    temperature_path=temperature_path,
                    orography_path=orography_path,
                    land_sea_mask_path=land_sea_mask_path,
                    output_path=output_path,
                    max_height_diff=max_height_diff,
                    nbhood_radius=nbhood_radius,
                    max_lapse_rate=max_lapse_rate,
                    min_lapse_rate=min_lapse_rate,
                    dry_adiabatic=dry_adiabatic,
                    config=config,
                )
            )
        )
        return 0


def dsc_temp_lapse_rate_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli lapse-rate`` 与直接运行本文件都进这里。"""
    return DscTempLapseRateCli().main(argv)


main = dsc_temp_lapse_rate_cli


if __name__ == "__main__":
    raise SystemExit(dsc_temp_lapse_rate_cli())
