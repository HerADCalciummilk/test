#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""由高分辨率地形和模式地形计算订正使用的 sigma 与轮廓粗糙度。

在本包目录执行::

    python cli/roughness_cli.py --orography-path PATH --model-orography-path MODEL.nc --sigma-output-path SIGMA.nc --silhouette-output-path AOS.nc

Python::

    from cli.roughness_cli import AncRoughnessCli
    AncRoughnessCli.call(
        orography_path="PATH",
        model_orography_path="MODEL.nc",
        sigma_output_path="SIGMA.nc",
        silhouette_output_path="AOS.nc",
    )
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
import xarray as xr
import meteva_base as meb


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    for entry in (str(temp_root), str(root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


_bootstrap_paths()

from utils.cli_base import CliBase


def process(
    orography_path: str,
    sigma_output_path: Optional[str] = None,
    silhouette_output_path: Optional[str] = None,
    *,
    model_orography_path: str,
    config=None,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """计算模式格点内高度标准差和轮廓粗糙度。

    参数
    ----------
    orography_path : str
        高分辨率地形高度场 nc，单位米。
    sigma_output_path, silhouette_output_path : str, optional
        输出路径。省略则不写对应文件。
    model_orography_path : str
        模式网格上的地形 nc。网格从该文件的 lat、lon 读取。

    返回
    -------
    sigma, silhouette
        模式格点高度标准差（米）和轮廓粗糙度（无量纲），都在高分辨率网格上。
    """
    del config
    from orographic_wind_downscaling.src.roughness import RoughnessCalculation

    orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(orography_path),
        is_single=True,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    model_orography = meb.checkout_griddata(
        meb.read_griddata_from_nc(model_orography_path),
        is_single=True,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    sigma, silhouette = RoughnessCalculation()(orography, model_orography)
    if sigma_output_path is not None:
        _write(sigma, sigma_output_path)
    if silhouette_output_path is not None:
        _write(silhouette, silhouette_output_path)
    return sigma, silhouette


def _write(data: xr.DataArray, output_path: str) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    name = data.name or "roughness"
    data.name = name
    data.astype(np.float32, copy=False).to_dataset(name=name).to_netcdf(target)


class AncRoughnessCli(CliBase):
    """``anc_roughness`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/roughness_cli.py"
    description = "按模式格点计算高度标准差 sigma 和轮廓粗糙度。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/roughness_cli.py --orography-path PATH --model-orography-path MODEL.nc "
        "--sigma-output-path SIGMA.nc --silhouette-output-path AOS.nc\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--orography-path", required=True, metavar="PATH", help="高分辨率地形高度场 NetCDF。必填。")
        parser.add_argument("--model-orography-path", required=True, metavar="PATH", help="模式网格上的地形 NetCDF。必填。")
        parser.add_argument("--sigma-output-path", default=None, metavar="PATH", help="高度标准差输出。省略则不写。")
        parser.add_argument("--silhouette-output-path", default=None, metavar="PATH", help="轮廓粗糙度输出。省略则不写。")

    def run(self, **params) -> int:
        process(**params)
        return 0


def anc_roughness_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。"""
    return AncRoughnessCli().main(argv)


main = anc_roughness_cli


if __name__ == "__main__":
    raise SystemExit(anc_roughness_cli())
