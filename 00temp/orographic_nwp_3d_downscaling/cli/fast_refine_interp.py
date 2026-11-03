"""CLI for fast refined interpolation. 参数定义在 ``orographic_nwp_3d_downscaling_cli``。"""
from __future__ import annotations

from .orographic_nwp_3d_downscaling_cli import (
    build_parser,
    orographic_nwp_3d_downscaling_cli as main,
)

__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
