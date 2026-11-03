# -*- coding: utf-8 -*-
"""在本包目录执行：``python -m cli``。"""
from .wind_fft_blending_cli import _build_arg_parser, wind_fft_blending_cli


def main(argv=None):
    return wind_fft_blending_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
