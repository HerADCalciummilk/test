"""统一命令行入口。在本包目录执行 ``python -m cli``。"""
from __future__ import annotations

from .steps_multi_time_fusion_cli import (
    main,
    parse_args,
    steps_multi_time_fusion_cli,
)

__all__ = [
    "main",
    "parse_args",
    "steps_multi_time_fusion_cli",
]
