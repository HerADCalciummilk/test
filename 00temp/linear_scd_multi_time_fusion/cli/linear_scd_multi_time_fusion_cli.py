# -*- coding: utf-8 -*-
"""SCD 双源配对融合。

``python -m cli`` 或 ``python -m linear_scd_multi_time_fusion`` 走本入口。
``history_range`` 写成 ``START,END``（UTC，YYYYMMDDHHMM）；省略则按配置做实时批次。
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

from utils.merge_params import merge_params


def _history(history_range):
    """把 ``START,END`` 或二元序列收成两个时次。省略则实时模式。"""
    if history_range is None or history_range == "":
        return []
    if isinstance(history_range, (list, tuple)):
        items = [str(item).strip() for item in history_range if str(item).strip()]
    else:
        items = [item.strip() for item in str(history_range).replace(" ", ",").split(",") if item.strip()]
    if len(items) not in (0, 2):
        raise ValueError("history range must be omitted or contain exactly START_UTC END_UTC.")
    return items


@merge_params()
def process(
    history_range=None,
    config=None,
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
    """合并配置后调用 ``ScdFusionPlugin``。"""
    from linear_scd_multi_time_fusion.src.scd_fusion_plugin import ScdFusionPlugin

    # 未传的项由插件按 ini 保留；空字符串仍是显式空值
    ScdFusionPlugin().process(
        history_range=_history(history_range),
        config=config,
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
