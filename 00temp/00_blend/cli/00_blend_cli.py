# -*- coding: utf-8 -*-
"""权重融合调度。

预报场和评分场是 iris Cube，由调用方传入。无 Cube 时只打印已合并的配置。
"""
from __future__ import annotations

import os
import sys
from functools import partial

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_TEMP_DIR = os.path.dirname(_ROOT_DIR)
for _p in (_TEMP_DIR, _ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from util_plugin import power_weight
from utils.merge_params import merge_params


@merge_params(section="blend")
def process(
    weight_power: float = -2.0,
    tolerate_period_mismatch: bool = False,
    fcst_cubes=None,
    factor_cubes=None,
    config=None,
):
    """按评分权重融合。``config`` 只换配置文件。给出两组 Cube 时调用插件。"""
    _ = config
    from weight_blending import WeightBlending

    plugin = WeightBlending(
        wfunc=partial(power_weight, power=float(weight_power)),
        tolerate_period_mismatch=bool(tolerate_period_mismatch),
    )
    if fcst_cubes is None or factor_cubes is None:
        print("weight_blending")
        print(
            "weight = score ** %s; tolerate_period_mismatch=%s"
            % (weight_power, tolerate_period_mismatch)
        )
        print("格点评分会再做 51x51 均值平滑。传入 fcst_cubes 与 factor_cubes 后执行融合。")
        return 0
    return plugin.process(fcst_cubes, factor_cubes)
