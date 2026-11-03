# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .frequency_matching_rain01_cli import (
    _build_arg_parser,
    frequency_matching_rain01_cli,
)


def main(argv=None):
    return frequency_matching_rain01_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
