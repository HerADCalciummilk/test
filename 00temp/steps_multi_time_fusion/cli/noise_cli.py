# -*- coding: utf-8 -*-
"""生成 STEPS AR(2) 噪声。未传的项读 ``[noise]``，再没有用预设。"""
from __future__ import annotations

import os
import sys

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

from steps_multi_time_fusion.src.noise_plugin import StepsNoisePlugin
from steps_multi_time_fusion.utils.util_env import resolve_noise
from utils.merge_params import merge_params


@merge_params(section="cli")
def process(
    mode: str = None,
    output_dir: str = None,
    issue_time: str = None,
    n_levels: int = None,
    phi1: float = None,
    phi2: float = None,
    n_ens_members: int = None,
    timesteps: int = None,
    config=None,
):
    """按解析后的参数调用 ``StepsNoisePlugin``。"""
    # section=cli 只合并模块名；各字段仍由 resolve_noise 按 [noise] 补齐并展开路径
    resolved = resolve_noise(
        mode=mode,
        output_dir=output_dir,
        issue_time=issue_time,
        n_levels=n_levels,
        phi1=phi1,
        phi2=phi2,
        n_ens_members=n_ens_members,
        timesteps=timesteps,
        config=config,
    )
    plugin = StepsNoisePlugin(
        output_dir=resolved["output_dir"],
        issue_time=resolved["issue_time"],
        n_levels=resolved["n_levels"],
        phi1=resolved["phi1"],
        phi2=resolved["phi2"],
        n_ens_members=resolved["n_ens_members"],
        timesteps=resolved["timesteps"],
    )
    plugin.process(resolved["mode"])
    return 0
