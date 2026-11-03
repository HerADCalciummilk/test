# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .interp_sg_cressman_cli import _build_parser, interp_sg_cressman_cli


def main(argv=None):
    return interp_sg_cressman_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
