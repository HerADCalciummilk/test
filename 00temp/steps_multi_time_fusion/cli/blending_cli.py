# -*- coding: utf-8 -*-
"""对两个二维 npy 降水场做 STEPS 融合。未传的项读 ``[blending]``，再没有用预设。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import numpy as np

from steps_multi_time_fusion.src.steps_blending_plugin import StepsBlendingPlugin
from steps_multi_time_fusion.utils.util_env import resolve_blending
from utils.merge_params import merge_params


@merge_params(section="cli")
def process(
    nowcast: str = None,
    nwp: str = None,
    output: str = None,
    lead_index: int = None,
    n_cascade_levels: int = None,
    tau_min: float = None,
    clim_skill: str = None,
    config=None,
):
    """读入两路降水，调用 ``StepsBlendingPlugin`` 后写出。"""
    resolved = resolve_blending(
        nowcast=nowcast,
        nwp=nwp,
        output=output,
        lead_index=lead_index,
        n_cascade_levels=n_cascade_levels,
        tau_min=tau_min,
        clim_skill=clim_skill,
        config=config,
    )
    nowcast_arr = np.load(resolved["nowcast"])
    nwp_arr = np.load(resolved["nwp"])
    plugin = StepsBlendingPlugin(
        n_cascade_levels=resolved["n_cascade_levels"],
        tau_min=resolved["tau_min"],
        use_climatological_skill=bool(resolved["clim_skill"]),
        climatological_skill_path=resolved["clim_skill"],
    )
    result = plugin.process(nowcast_arr, nwp_arr, lead_index=resolved["lead_index"])
    output_path = Path(resolved["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, result)
    print("融合结果已保存：%s，形状=%s" % (output_path, result.shape))
    return 0
