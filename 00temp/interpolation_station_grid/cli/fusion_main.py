"""网格站点融合命令行。参数定义在 ``interpolation_station_grid_cli``。"""
from __future__ import annotations

from .interpolation_station_grid_cli import build_parser, interpolation_station_grid_cli as main

__all__ = ["build_parser", "main"]
