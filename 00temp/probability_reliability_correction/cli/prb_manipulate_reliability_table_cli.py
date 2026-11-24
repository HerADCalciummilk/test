#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""整理可靠性表命令行。

网格：``output_path`` 为目录（按阈值多文件）；站点：为单个 csv。

在本包目录执行::

    python -m cli manipulate --reliability-table-path PATH
    python cli/prb_manipulate_reliability_table.py --reliability-table-path PATH

Python::

    from cli.prb_manipulate_reliability_table import PrbManipulateReliabilityTableCli
    PrbManipulateReliabilityTableCli.call(reliability_table_path="PATH")
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence, Union


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    root_s = str(root)
    parent_s = str(parent)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if parent_s not in sys.path:
        sys.path.append(parent_s)


_bootstrap_paths()

import pandas as pd
import xarray as xr

from utils.merge_params import merge_params


@merge_params()
def process(
    reliability_table_path: Union[str, Path],
    *,
    minimum_forecast_count: int = 200,
    point_by_point: bool = False,
    output_path: Optional[Union[str, Path]] = None, config=None) -> Union[List[xr.Dataset], pd.DataFrame]:
    """读取可靠性表，合并欠采样箱并强制观测频率单调，可选写出。

    参数
    ----------
    reliability_table_path :
        可靠性表路径；
        网格 ``.nc`` 或站点 ``.csv``。
    minimum_forecast_count :
        概率箱最少预报计数；低于该值将尝试与邻箱合并。
    point_by_point :
        是否按空间点 / 站点分别整理。
    output_path :
        网格为输出目录；站点为输出 csv；``None`` 只返回。

    返回
    -------
    list of xr.Dataset 或 pd.DataFrame
        网格按阈值拆开的表列表，或站点一张长表。
    """
    from probability_reliability_correction.cli.io import read_reliability, write_result
    from probability_reliability_correction.src.reliability_calibration import (
        ManipulateReliabilityTable,
    )

    table = read_reliability(reliability_table_path)
    result = ManipulateReliabilityTable(
        minimum_forecast_count=minimum_forecast_count,
        point_by_point=point_by_point,
    ).process(table)
    if output_path is not None:
        written = write_result(result, output_path)
        if written is not None:
            print("已写出", len(written), "个阈值表 ->", Path(output_path))
    return result


