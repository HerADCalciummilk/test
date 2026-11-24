# -*- coding: utf-8 -*-
"""STEPS 多时效融合。``module`` 选择 noise、climatological_skill（或 skill）、blending。

各命令自己的键在对应 ``*_cli.py`` 上。这里只按 module 转发调用方显式给出的项。
"""
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

from steps_multi_time_fusion.utils.util_env import resolve_module
from utils.merge_params import merge_params


@merge_params(section="cli")
def process(
    module: str = None,
    config=None,
    mode: str = None,
    output_dir: str = None,
    issue_time: str = None,
    n_levels: int = None,
    phi1: float = None,
    phi2: float = None,
    n_ens_members: int = None,
    timesteps: int = None,
    input_dir: str = None,
    output: str = None,
    nowcast: str = None,
    nwp: str = None,
    lead_index: int = None,
    n_cascade_levels: int = None,
    tau_min: float = None,
    clim_skill: str = None,
):
    """按 module 调用对应命令的 process。"""
    name = resolve_module(module, config=config)
    if name == "noise":
        from .noise_cli import process as run

        return run(
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
    if name == "climatological_skill":
        from .climatological_skill_cli import process as run

        return run(input_dir=input_dir, output=output, config=config)
    from .blending_cli import process as run

    return run(
        nowcast=nowcast,
        nwp=nwp,
        output=output,
        lead_index=lead_index,
        n_cascade_levels=n_cascade_levels,
        tau_min=tau_min,
        clim_skill=clim_skill,
        config=config,
    )
