# -*- coding: utf-8 -*-
"""兼容 ``from src.main import process``。调度在 CLI。"""
from __future__ import annotations


def process(*args, **kwargs):
    from cli.weather_phenom_grid_12h_cli import process as run

    return run(*args, **kwargs)
