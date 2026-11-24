# -*- coding: utf-8 -*-
"""临近光流外推统一入口。``module`` 选择算法。"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
for _p in (_ROOT_DIR, _CLI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from utils.cli_grid_io import load_precip_griddata_list, load_velocity_griddata
from utils.merge_params import merge_params
from utils.util_env import MODULES, resolve_args

from src.extrapolation_plugin import Extrapolation
from src.linda_plugin import Linda
from src.lk_plugin import LK
from src.lsqr_optical_flow_plugin import LsqrOpticalFlow
from src.sprog_plugin import Sprog
from src.steps_plugin import Steps


_MODULE_ALIASES = {
    "window-lsqr": "lsqr_optical_flow",
    "window_lsqr": "lsqr_optical_flow",
}


def _normalize_module(module: str) -> str:
    raw = (module or "steps").strip()
    name = _MODULE_ALIASES.get(raw, raw)
    if name not in MODULES:
        raise ValueError("module 无效。可选: %s" % (", ".join(MODULES),))
    return name


def _pert_thrs(value):
    parts = [item.strip() for item in str(value).split(",") if item.strip()]
    if len(parts) != 2:
        raise ValueError("pert_thrs 需要两个数值，收到: %r" % (value,))
    return float(parts[0]), float(parts[1])


def _process(module, cfg):
    """按 module 跑一次算法。"""
    if module == "lk":

        LK(
            transform_method=cfg["transform_method"],
            fd_method=cfg["fd_method"],
            interp_method=cfg["interp_method"],
            dense=cfg["dense"],
            nr_std_outlier=cfg["nr_std_outlier"],
            k_outlier=cfg["k_outlier"],
            size_opening=cfg["size_opening"],
            decl_scale=cfg["decl_scale"],
            verbose=cfg["verbose"],
        ).process(load_precip_griddata_list(cfg["precip"]))
        return
    if module == "lsqr_optical_flow":

        LsqrOpticalFlow(
            min_window=cfg["min_window"],
            rain_limit=cfg["rain_limit"],
            delta_rain_limit=cfg["delta_rain_limit"],
            num_limit=cfg["num_limit"],
            lsqr_damp=cfg["lsqr_damp"],
            verbose=cfg["verbose"],
        ).process(
            load_precip_griddata_list(cfg["precip_before"]),
            load_precip_griddata_list(cfg["precip_next"]),
        )
        return
    if module == "extrapolation":

        Extrapolation(
            extrap_method=cfg["extrap_method"],
            measure_time=cfg["measure_time"],
        ).process(
            load_precip_griddata_list(cfg["precip"]),
            load_velocity_griddata(cfg["velocity"]),
            cfg["timesteps"],
            delta_t=timedelta(minutes=int(cfg["delta_min"])),
        )
        return
    if module == "sprog":

        Sprog(
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
        ).process(
            load_precip_griddata_list(cfg["precip"]),
            load_velocity_griddata(cfg["velocity"]),
            cfg["timesteps"],
            delta_t=timedelta(minutes=int(cfg["delta_min"])),
        )
        return
    if module == "linda":

        Linda(
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
        ).process(
            load_precip_griddata_list(cfg["precip"]),
            load_velocity_griddata(cfg["velocity"]),
            cfg["timesteps"],
            delta_t=timedelta(minutes=int(cfg["delta_min"])),
        )
        return

    Steps(
        n_ens_members=cfg["n_ens_members"],
        n_cascade_levels=cfg["n_cascade_levels"],
        precip_thr=cfg["precip_thr"],
        kmperpixel=cfg["kmperpixel"],
        timestep=cfg["timestep"],
        extrap_method=cfg["extrap_method"],
        decomp_method=cfg["decomp_method"],
        bandpass_filter_method=cfg["bandpass_filter_method"],
        noise_method=cfg["noise_method"],
        noise_stddev_adj=cfg["noise_stddev_adj"],
        ar_order=cfg["ar_order"],
        vel_pert_method=cfg["vel_pert_method"],
        conditional=cfg["conditional"],
        probmatching_method=cfg["probmatching_method"],
        mask_method=cfg["mask_method"],
        seed=cfg["seed"],
        num_workers=cfg["num_workers"],
        fft_method=cfg["fft_method"],
        domain=cfg["domain"],
        measure_time=cfg["measure_time"],
        return_output=cfg["return_output"],
    ).process(
        load_precip_griddata_list(cfg["precip"]),
        load_velocity_griddata(cfg["velocity"]),
        cfg["timesteps"],
        delta_t=timedelta(minutes=int(cfg["delta_min"])),
    )


@merge_params(section="cli")
def process(module: str = "steps", config=None, **kwargs):
    """其余 ``key=value`` 只作用于当前 ``module`` 对应 ini 节。"""
    mod = _normalize_module(module)
    explicit = {key: value for key, value in kwargs.items() if value is not None}
    cfg = resolve_args(mod, config=config, **explicit)
    _process(mod, cfg)
