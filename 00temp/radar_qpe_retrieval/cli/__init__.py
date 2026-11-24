#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""radar_qpe_retrieval 模块 CLI 菜单。"""

from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None):
    """列出本包命令行入口。"""
    del argv
    lines = [
        "radar_qpe_retrieval 命令行（在本包目录执行，先看 --help）：",
        "",
        "极坐标质控：",
        "  python cli/radar_qc_cli.py --help",
        "  python cli/radar_qc_cli.py --input-path PATH "
        "[--dem-path DEM] [--refl-output-path OUT] [--config PATH]",
        "  python -m cli.radar_qc_cli --help",
        "",
        "基数据→经纬网格（附属，无质控；轻量读入，无 cinrad）：",
        "  python cli/radar_grid_cli.py --help",
        "  python cli/radar_grid_cli.py --input-path PATH --output-dir OUT "
        "[--fields REF,KDP] [--radius 230]",
        "  python -m cli.radar_grid_cli --help",
        "",
        "QPE 降水反演：",
        "  python cli/qpe.py --help",
        "  python cli/qpe.py --method z --refl-path PATH [--output-path PATH] [--config PATH]",
        "  python -m cli.qpe --help",
    ]
    print("\n".join(lines))
    return 0
