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
        "  python cli/meta_orographic_enhancement_cli.py --help",
        "  python -m cli.meta_orographic_enhancement_cli --help",
        "",
        "  python cli/orographic_enhancement_cli.py --help",
        "  python -m cli.orographic_enhancement_cli --help",
        "",
        "  python cli/apply_orographic_enhancement_cli.py --help",
        "  python -m cli.apply_orographic_enhancement_cli --help",
        "",
        "  python cli/redistribute_cascade_cli.py --help",
        "  python cli/redistribute_cascade_cli.py --precip-path PATH --temperature-path PATH --humidity-path PATH --pressure-path PATH --uwind-path PATH --vwind-path PATH --orography-model-path PATH --orography-target-path PATH --stages 20,5,1 [--output-path PATH]",
        "  python -m cli.redistribute_cascade_cli --help",
        "",
        "预处理脚本仍直接运行：",
        "  python cli/preprocess_test_data.py",
    ]
    print("\n".join(lines))
    return 0
