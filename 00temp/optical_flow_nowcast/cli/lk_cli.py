# -*- coding: utf-8 -*-
"""Lucas-Kanade 光流。"""
from __future__ import annotations

import os
import sys

_CLI = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_CLI)
for _p in (_CLI, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.lk_plugin import LK
from utils.cli_grid_io import load_precip_griddata_list
from utils.merge_params import merge_params
from utils.util_env import resolve_args


@merge_params(section="cli")
def process(config=None, **kwargs):
    explicit = {key: value for key, value in kwargs.items() if value is not None}
    cfg = resolve_args("lk", config=config, **explicit)
    plugin = LK(
        transform_method=cfg["transform_method"],
        fd_method=cfg["fd_method"],
        interp_method=cfg["interp_method"],
        dense=cfg["dense"],
        nr_std_outlier=cfg["nr_std_outlier"],
        k_outlier=cfg["k_outlier"],
        size_opening=cfg["size_opening"],
        decl_scale=cfg["decl_scale"],
        verbose=cfg["verbose"],
    )
    plugin.process(load_precip_griddata_list(cfg["precip"]))
