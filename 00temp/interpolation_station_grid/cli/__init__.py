"""CLI 入口：``process``（已挂 ``@merge_params``）。命令行请在 00temp 执行 ``python -m interpolation_station_grid key=value``。"""
from .interpolation_station_grid_cli import process

__all__ = ["process"]
