#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""qpe 模块 CLI 入口。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出带路径参数的命令行。"""
    del argv
    lines = [
        "qpe 命令行参数由 flags 传入，先看 --help：",
        "  python cli/qpe.py --help",
        "  python cli/qpe.py --method z --refl-path PATH [--kdp-path PATH] [--output-path PATH] [--config PATH]",
        "  python -m cli.qpe --help",
    ]
    print("\n".join(lines))
    return 0
