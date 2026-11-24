# -*- coding: utf-8 -*-
"""兼容 ``from main import process``。调度在 ``cli/wind_fft_blending_cli.py``。"""
from __future__ import annotations


def process(*args, **kwargs):
    from cli.wind_fft_blending_cli import process as run

    return run(*args, **kwargs)
