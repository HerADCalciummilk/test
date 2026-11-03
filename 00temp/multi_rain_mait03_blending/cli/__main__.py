# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .multi_rain_mait03_blending_cli import (
    _build_parser,
    multi_rain_mait03_blending_cli,
)


def main(argv=None):
    return multi_rain_mait03_blending_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
