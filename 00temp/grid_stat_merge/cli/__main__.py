# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .grid_stat_merge_cli import _build_parser, grid_stat_merge_cli


def main(argv=None):
    return grid_stat_merge_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
