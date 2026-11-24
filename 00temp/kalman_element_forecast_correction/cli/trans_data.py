# -*- coding: utf-8 -*-
"""拷贝入口别名。参数表只在 ``kalman_element_forecast_correction_cli.process``。"""
from __future__ import annotations


def run(**kwargs):
    from .kalman_element_forecast_correction_cli import process

    kwargs.setdefault("module", "trans")
    return process(**kwargs)
