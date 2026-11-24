#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""聚合可靠性表命令行。

输入由后缀决定：``.nc`` 网格表；``.csv`` 站点长表。

在本包目录执行::

    python -m cli aggregate --reliability-table-paths PATH
    python cli/prb_aggregate_reliability_tables.py --reliability-table-paths PATH

Python::

    from cli.prb_aggregate_reliability_tables import PrbAggregateReliabilityTablesCli
    PrbAggregateReliabilityTablesCli.call(reliability_table_paths=["PATH"])
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence, Union


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
    reliability_table_paths: Sequence[Union[str, Path]],
    *,
    coordinates: Optional[Sequence[str]] = None,
    output_path: Optional[Union[str, Path]] = None, config=None) -> Union[xr.Dataset, pd.DataFrame]:
    """读取一张或多张可靠性表，按坐标求和聚合并可选写出。

    参数
    ----------
    reliability_table_paths :
        可靠性表路径；
        网格 ``.nc`` 或站点 ``.csv`` 路径列表（不可混用）。
    coordinates :
        要求和的坐标，例如网格 ``["lat", "lon"]``、站点 ``["id"]``；
        ``None`` 表示多表合并时不对空间/站点维求和。
    output_path :
        若给出则写出结果；``None`` 只返回。

    返回
    -------
    xr.Dataset 或 pd.DataFrame
        聚合后的可靠性表。
    """
    from probability_reliability_correction.cli.io import read_reliabilities, write_result
    from probability_reliability_correction.src.reliability_calibration import (
        AggregateReliabilityCalibrationTables,
    )

    tables = read_reliabilities(reliability_table_paths)
    result = AggregateReliabilityCalibrationTables().process(
        tables,
        coordinates=None if coordinates is None else list(coordinates),
    )
    if output_path is not None:
        write_result(result, output_path)
    return result


