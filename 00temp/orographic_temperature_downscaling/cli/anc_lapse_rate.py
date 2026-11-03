#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""应用层结递减率进行温度地形订正的命令行。

在本包目录执行::

    python -m cli apply-lapse --temperature-path PATH --lapse-rate-path PATH --source-orography-path PATH --target-orography-path PATH
    python cli/anc_lapse_rate.py --temperature-path PATH --lapse-rate-path PATH --source-orography-path PATH --target-orography-path PATH

Python::

    from cli.anc_lapse_rate import AncLapseRateCli
    AncLapseRateCli.call(
        temperature_path="PATH",
        lapse_rate_path="PATH",
        source_orography_path="PATH",
        target_orography_path="PATH",
    )
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Union


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

def process(
    temperature_path: str,
    lapse_rate_path: str,
    source_orography_path: str,
    target_orography_path: str,
    output_path: Optional[str] = None, config=None) -> Union[xr.DataArray, np.ndarray]:
    """将已计算的层结递减率应用到温度场。

    参数
    ----------
    temperature_path : str
        输入温度场 nc 文件路径。
    lapse_rate_path : str
        层结递减率场 nc 文件路径，单位通常为 ``K m-1``。
    source_orography_path : str
        温度原始网格对应的源地形高度场 nc 文件路径。
    target_orography_path : str
        目标地形高度场 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径；为 None 时不写文件，仅返回结果。

    返回
    -------
    xr.DataArray or np.ndarray
        地形订正后的温度场。
    """
    from orographic_temperature_downscaling.src.lapse_rate import ApplyGriddedLapseRate
        
    _unbounded = (-np.inf, np.inf, np.nan)

    temperature = meb.read_griddata_from_nc(temperature_path)
    lapse_rate = meb.read_griddata_from_nc(lapse_rate_path)
    source_orography = meb.read_griddata_from_nc(source_orography_path)
    target_orography = meb.read_griddata_from_nc(target_orography_path)

    temperature = meb.checkout_griddata(temperature, valid_val=_unbounded)
    lapse_rate = meb.checkout_griddata(lapse_rate)
    source_orography = meb.checkout_griddata(source_orography, valid_val=_unbounded)
    target_orography = meb.checkout_griddata(target_orography, valid_val=_unbounded)

    if not meb.checkout_griddata_same_coords([temperature, lapse_rate], is_time_match=True):
        raise ValueError("层结递减率场与温度场的空间/时效坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, source_orography], is_time_match=False):
        raise ValueError("源地形高度场与温度场的坐标不一致")
    if not meb.checkout_griddata_same_coords([temperature, target_orography], is_time_match=False):
        raise ValueError("目标地形高度场与温度场的坐标不一致")

    result = ApplyGriddedLapseRate()(
        temperature,
        lapse_rate,
        source_orography,
        target_orography,
    )

    if output_path is not None:
        meb.write_griddata_to_nc(result, output_path, creat_dir=True)

    return result


def _omit_none(kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


_CONFIG_HELP = (
    "运行配置文件，传给 process 的 config。"
    "省略则为 None，process 使用各参数自身的默认值。"
)


class AncLapseRateCli(CliBase):
    """应用层结递减率订正温度。``run`` 调用 ``process``。"""

    prog = "python cli/anc_lapse_rate.py"
    description = "将已计算的层结递减率应用到温度场。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli apply-lapse --help\n"
        "  python -m cli apply-lapse --temperature-path PATH --lapse-rate-path PATH "
        "--source-orography-path PATH --target-orography-path PATH --output-path PATH\n"
        "  python cli/anc_lapse_rate.py --temperature-path PATH --lapse-rate-path PATH "
        "--source-orography-path PATH --target-orography-path PATH\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--temperature-path", required=True, metavar="PATH", help="输入温度场 nc。")
        parser.add_argument("--lapse-rate-path", required=True, metavar="PATH", help="层结递减率场 nc，单位通常为 K m-1。")
        parser.add_argument("--source-orography-path", required=True, metavar="PATH", help="源地形高度场 nc。")
        parser.add_argument("--target-orography-path", required=True, metavar="PATH", help="目标地形高度场 nc。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="输出 nc。省略则不写文件。")
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        temperature_path,
        lapse_rate_path,
        source_orography_path,
        target_orography_path,
        output_path=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    temperature_path=temperature_path,
                    lapse_rate_path=lapse_rate_path,
                    source_orography_path=source_orography_path,
                    target_orography_path=target_orography_path,
                    output_path=output_path,
                    config=config,
                )
            )
        )
        return 0


def anc_lapse_rate_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli apply-lapse`` 与直接运行本文件都进这里。"""
    return AncLapseRateCli().main(argv)


main = anc_lapse_rate_cli


if __name__ == "__main__":
    raise SystemExit(anc_lapse_rate_cli())