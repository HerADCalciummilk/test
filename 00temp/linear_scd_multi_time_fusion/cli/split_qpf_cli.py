# -*- coding: utf-8 -*-
"""把 unet_qpf 与 mait_st 拆成对齐的 10 分钟场。

默认读 ``resource/split_config.ini``。``daemon=true`` 时按其中的调度节循环。
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

from .linear_scd_multi_time_fusion_cli import _history
from utils.merge_params import merge_params


def _as_bool(value, default=False):
    """命令行传来的 true/false 字符串按布尔理解。"""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


@merge_params(ini_path="resource/split_config.ini", section="runtime")
def process(
    history_range=None,
    config=None,
    daemon=None,
    allowed_realtime_minutes=None,
    history_step_minutes=None,
    dry_run=None,
    max_files=None,
    source1_dir=None,
    source2_dir=None,
    truth_dir=None,
    output_dir=None,
    enabled=None,
    time_step_minutes=None,
    overwrite=None,
    blending_type=None,
    keyframe_weights=None,
    lon_min=None,
    lon_max=None,
    lat_min=None,
    lat_max=None,
    output_var=None,
    output_source=None,
):
    """合并拆分配置后调用 ``QpfSplitPlugin``。"""
    from linear_scd_multi_time_fusion.src.qpf_split_plugin import QpfSplitPlugin

    QpfSplitPlugin().process(
        history_range=_history(history_range),
        config=config,
        daemon=_as_bool(daemon),
        allowed_realtime_minutes=allowed_realtime_minutes,
        history_step_minutes=history_step_minutes,
        dry_run=dry_run,
        max_files=max_files,
        source1_dir=source1_dir,
        source2_dir=source2_dir,
        truth_dir=truth_dir,
        output_dir=output_dir,
        enabled=enabled,
        time_step_minutes=time_step_minutes,
        overwrite=overwrite,
        blending_type=blending_type,
        keyframe_weights=keyframe_weights,
        lon_min=lon_min,
        lon_max=lon_max,
        lat_min=lat_min,
        lat_max=lat_max,
        output_var=output_var,
        output_source=output_source,
    )
    return 0
