# -*- coding: utf-8 -*-
"""LINDA 临近外推。"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

_CLI = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_CLI)
for _p in (_CLI, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.linda_plugin import Linda
from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata
from utils.merge_params import merge_params
from utils.util_env import resolve_args


def _pert_thrs(value):
    parts = [item.strip() for item in str(value).split(",") if item.strip()]
    if len(parts) != 2:
        raise ValueError("pert_thrs 需要两个数值，收到: %r" % (value,))
    return float(parts[0]), float(parts[1])


@merge_params(section="cli")
def process(config=None, **kwargs):
    explicit = {key: value for key, value in kwargs.items() if value is not None}
    cfg = resolve_args("linda", config=config, **explicit)
    plugin = Linda(
        add_perturbations=cfg["add_perturbations"],
        feature_method=cfg["feature_method"],
        max_num_features=cfg["max_num_features"],
        ari_order=cfg["ari_order"],
        kernel_type=cfg["kernel_type"],
        localization_window_radius=cfg["localization_window_radius"],
        errdist_window_radius=cfg["errdist_window_radius"],
        acf_window_radius=cfg["acf_window_radius"],
        extrap_method=cfg["extrap_method"],
        pert_thrs=_pert_thrs(cfg["pert_thrs"]),
        n_ens_members=cfg["n_ens_members"],
        vel_pert_method=cfg["vel_pert_method"],
        kmperpixel=cfg["kmperpixel"],
        timestep=cfg["timestep"],
        num_workers=cfg["num_workers"],
        seed=cfg["seed"],
        use_multiprocessing=cfg["use_multiprocessing"],
        measure_time=cfg["measure_time"],
        return_output=cfg["return_output"],
    )
    plugin.process(
        load_precip_griddata_list(cfg["precip"]),
        load_velocity_griddata(cfg["velocity"]),
        cfg["timesteps"],
        delta_t=timedelta(minutes=int(cfg["delta_min"])),
    )
