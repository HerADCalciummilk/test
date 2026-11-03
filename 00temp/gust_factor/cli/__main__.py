# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .gust_factor_cli import _build_parser, gust_factor_cli


def main(argv=None):
    return gust_factor_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
