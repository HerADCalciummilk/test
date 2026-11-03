"""网格站点融合命令行。参数定义在 ``station_grid_fusion_cli``。"""
from __future__ import annotations

from .station_grid_fusion_cli import build_parser, station_grid_fusion_cli as main

__all__ = ["build_parser", "main"]
