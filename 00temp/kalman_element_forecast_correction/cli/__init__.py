"""统一命令行入口。在本包目录执行 ``python -m cli``。"""
from __future__ import annotations

from .kalman_element_forecast_correction_cli import (
    kalman_element_forecast_correction_cli,
    main,
    parse_args,
)

__all__ = [
    "kalman_element_forecast_correction_cli",
    "main",
    "parse_args",
]
