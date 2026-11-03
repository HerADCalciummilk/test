#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""neighbourhood_probability_processing 模块 CLI 入口。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出带路径参数的命令行。"""
    del argv
    lines = [
        "邻域概率命令行参数由 flags 传入，先看 --help：",
        "  python cli/ens_nbhood.py --help",
        "  python cli/ens_nbhood.py --input-data-path PATH --neighbourhood-output probabilities --radii 20000 [--output-path PATH] [--config PATH]",
        "  python -m cli.ens_nbhood --help",
        "  python cli/ens_nbhood_land_and_sea.py --help",
        "  python cli/ens_nbhood_land_and_sea.py --input-data-path PATH --mask-path PATH --radii 20000 [--output-path PATH] [--config PATH]",
        "  python -m cli.ens_nbhood_land_and_sea --help",
        "  python cli/ens_nbhood_iterate_with_mask.py --help",
        "  python cli/ens_nbhood_iterate_with_mask.py --input-data-path PATH --mask-path PATH --coord-for-masking level --radii 10000 [--output-path PATH] [--config PATH]",
        "  python -m cli.ens_nbhood_iterate_with_mask --help",
        "",
        "官方样例预处理仍直接运行：",
        "  python cli/preprocess_test_data.py",
    ]
    print("\n".join(lines))
    return 0
