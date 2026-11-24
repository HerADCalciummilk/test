# -*- coding: utf-8 -*-
"""S-PROG 临近外推。"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

_CLI = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_CLI)
for _p in (_CLI, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.sprog_plugin import Sprog
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata
from utils.merge_params import merge_params
from utils.util_env import resolve_args


@merge_params(section="cli")
def process(config=None, **kwargs):
    explicit = {key: value for key, value in kwargs.items() if value is not None}
    cfg = resolve_args("sprog", config=config, **explicit)
    plugin = Sprog(
        precip_thr=cfg["precip_thr"],
        n_cascade_levels=cfg["n_cascade_levels"],
        extrap_method=cfg["extrap_method"],
        decomp_method=cfg["decomp_method"],
        bandpass_filter_method=cfg["bandpass_filter_method"],
        ar_order=cfg["ar_order"],
        conditional=cfg["conditional"],
        probmatching_method=cfg["probmatching_method"],
        num_workers=cfg["num_workers"],
        fft_method=cfg["fft_method"],
        domain=cfg["domain"],
        measure_time=cfg["measure_time"],
    )
    plugin.process(
        load_precip_griddata_list(cfg["precip"]),
        load_velocity_griddata(cfg["velocity"]),
        cfg["timesteps"],
        delta_t=timedelta(minutes=int(cfg["delta_min"])),
    )
