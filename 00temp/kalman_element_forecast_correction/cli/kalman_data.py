# -*- coding: utf-8 -*-
"""订正入口别名。参数表只在 ``kalman_element_forecast_correction_cli.process``。"""
from __future__ import annotations


def run(**kwargs):
    from .kalman_element_forecast_correction_cli import process

    kwargs.setdefault("module", "kalman")
    return process(**kwargs)
