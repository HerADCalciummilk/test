#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""orographic_wind_downscaling 模块 CLI 入口。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出带路径参数的命令行。"""
    del argv
    lines = [
        "地形风速降尺度命令行参数由 flags 传入，先看 --help：",
        "  python cli/dsc_wind_downscaling.py --help",
        "  python cli/dsc_wind_downscaling.py --wind-speed-path PATH --sigma-path PATH --target-orography-path PATH --standard-orography-path PATH --silhouette-roughness-path PATH --model-resolution 1500 [--output-path PATH] [--config PATH]",
        "  python -m cli.dsc_wind_downscaling --help",
        "  python cli/roughness_cli.py --orography-path PATH --model-orography-path MODEL.nc --sigma-output-path SIGMA.nc --silhouette-output-path AOS.nc",
        "  python -m cli.roughness_cli --help",
        "",
        "输入为预处理后的 meb 六维 nc。预处理仍直接运行：",
        "  python cli/preprocess_test_data.py",
        "经纬与投影路径数值对照见 Notebook：nbs/wind_calculations.ipynb",
    ]
    print("\n".join(lines))
    return 0
