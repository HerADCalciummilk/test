"""统一命令行入口。在本包目录执行 ``python -m cli``。"""
from __future__ import annotations

from .kalman_element_forecast_correction_cli import process

__all__ = ["process"]
