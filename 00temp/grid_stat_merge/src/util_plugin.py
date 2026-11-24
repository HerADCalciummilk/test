# -*- coding: utf-8 -*-
"""格站融合计算。实现仍在 ``grid_stat_merge``，这里转给插件调用。"""
from __future__ import annotations


def __getattr__(name: str):
    from grid_stat_merge import diffuse_values, do_gs_merge, gaussian_2d, interp_sg_diffuse

    mapping = {
        "diffuse_values": diffuse_values,
        "do_gs_merge": do_gs_merge,
        "gaussian_2d": gaussian_2d,
        "interp_sg_diffuse": interp_sg_diffuse,
    }
    if name not in mapping:
        raise AttributeError(name)
    return mapping[name]
