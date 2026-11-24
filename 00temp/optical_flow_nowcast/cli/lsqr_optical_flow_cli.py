# -*- coding: utf-8 -*-
"""窗域 LSQR 光流（``lsqr_optical_flow``）。"""
from __future__ import annotations

import os
import sys

_CLI = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_CLI)
for _p in (_CLI, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.lsqr_optical_flow_plugin import LsqrOpticalFlow
from utils.cli_grid_io import load_precip_griddata_list
from utils.merge_params import merge_params
from utils.util_env import resolve_args


@merge_params(section="cli")
def process(config=None, **kwargs):
    explicit = {key: value for key, value in kwargs.items() if value is not None}
    cfg = resolve_args("lsqr_optical_flow", config=config, **explicit)
    plugin = LsqrOpticalFlow(
        min_window=cfg["min_window"],
        rain_limit=cfg["rain_limit"],
        delta_rain_limit=cfg["delta_rain_limit"],
        num_limit=cfg["num_limit"],
        lsqr_damp=cfg["lsqr_damp"],
        verbose=cfg["verbose"],
    )
    plugin.process(
        load_precip_griddata_list(cfg["precip_before"]),
        load_precip_griddata_list(cfg["precip_next"]),
    )
