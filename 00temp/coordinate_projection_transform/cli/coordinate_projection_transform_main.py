"""坐标投影转换 CLI。参数定义在 ``coordinate_projection_transform_cli``。"""
from __future__ import annotations

from .coordinate_projection_transform_cli import (
    build_parser,
    coordinate_projection_transform_cli as main,
)

__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
