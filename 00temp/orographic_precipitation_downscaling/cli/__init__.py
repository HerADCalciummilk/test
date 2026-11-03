#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""orographic_enhancement 模块 CLI 入口。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出带路径参数的命令行。"""
    del argv
    lines = [
        "地形降水增强命令行参数由 flags 传入，先看 --help：",
        "  python cli/dsc_orographic_enhancement.py --help",
        "  python cli/dsc_orographic_enhancement.py --temperature-path PATH --humidity-path PATH --pressure-path PATH --wind-speed-path PATH --wind-direction-path PATH --orography-path PATH [--output-path PATH] [--config PATH]",
        "  python -m cli.dsc_orographic_enhancement --help",
        "",
        "  python cli/dsc_orographic_enhancement_uv.py --help",
        "  python -m cli.dsc_orographic_enhancement_uv --help",
        "",
        "  python cli/dsc_apply_orographic_enhancement.py --help",
        "  python -m cli.dsc_apply_orographic_enhancement --help",
        "",
        "预处理脚本仍直接运行：",
        "  python cli/preprocess_test_data.py",
    ]
    print("\n".join(lines))
    return 0
