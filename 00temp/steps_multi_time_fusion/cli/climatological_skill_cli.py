# -*- coding: utf-8 -*-
"""汇总 daily_skill_*.npy。未传的项读 ``[climatological_skill]``，再没有用预设。"""
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

from steps_multi_time_fusion.src.climatological_skill_plugin import ClimatologicalSkillPlugin
from steps_multi_time_fusion.utils.util_env import resolve_climatological_skill
from utils.merge_params import merge_params


@merge_params(section="cli")
def process(
    input_dir: str = None,
    output: str = None,
    config=None,
):
    """读逐日技能文件，调用插件汇总气候态技能并写出。"""
    resolved = resolve_climatological_skill(
        input_dir=input_dir,
        output=output,
        config=config,
    )
    directory = Path(resolved["input_dir"])
    daily_files = sorted(directory.glob("daily_skill_*.npy"))
    if not daily_files:
        raise FileNotFoundError("未找到 daily_skill_*.npy: %s" % directory)
    # 逐日矩阵求几何平均，公式仍在插件里
    daily_skills = [np.load(path) for path in daily_files]
    clim_skill = ClimatologicalSkillPlugin.climatological_skill(daily_skills)
    output_path = Path(resolved["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(output_path, clim_skill)
    print("climatological skill 已保存：%s，形状=%s" % (output_path, clim_skill.shape))
    return 0
