# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .weather_phenom_grid_12h_cli import (
    _build_arg_parser,
    weather_phenom_grid_12h_cli,
)


def main(argv=None):
    return weather_phenom_grid_12h_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
