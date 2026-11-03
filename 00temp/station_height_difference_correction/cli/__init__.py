#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""station_height_difference_correction 模块 CLI 入口。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出带路径参数的命令行。"""
    del argv
    lines = [
        "站点高差订正命令行参数由 flags 传入，先看 --help：",
        "  python cli/dsc_estimate_dz_rescaling.py --help",
        "  python cli/dsc_estimate_dz_rescaling.py --forecast-path PATH --truth-path PATH --neighbour-path PATH --forecast-period 6 --forecast-data-name wind_speed [--output-path PATH] [--config PATH]",
        "  python -m cli.dsc_estimate_dz_rescaling --help",
        "  python cli/dsc_apply_dz_rescaling.py --help",
        "  python cli/dsc_apply_dz_rescaling.py --forecast-path PATH --scaled-dz-path PATH --forecast-data-name wind_speed [--output-path PATH] [--config PATH]",
        "  python -m cli.dsc_apply_dz_rescaling --help",
    ]
    print("\n".join(lines))
    return 0
