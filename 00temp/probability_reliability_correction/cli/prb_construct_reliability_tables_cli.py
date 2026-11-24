#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""构建可靠性表命令行。

输入由后缀决定：``.nc`` 网格六维场；``.csv`` 站点六列表（meb 表头 attrs）。

在本包目录执行::

    python -m cli construct --forecast-path PATH --truth-path PATH
    python cli/prb_construct_reliability_tables.py --forecast-path PATH --truth-path PATH

Python::

    from cli.prb_construct_reliability_tables import PrbConstructReliabilityTablesCli
    PrbConstructReliabilityTablesCli.call(forecast_path="PATH", truth_path="PATH")
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
    forecast_path: Union[str, Path],
    truth_path: Union[str, Path],
    *,
    n_probability_bins: int = 5,
    single_value_lower_limit: bool = False,
    single_value_upper_limit: bool = False,
    aggregate_coords: Optional[Sequence[str]] = None,
    output_path: Optional[Union[str, Path]] = None, config=None) -> Union[xr.Dataset, pd.DataFrame]:
    """读取预报/实况，构建可靠性表并可选写出。

    参数
    ----------
    forecast_path, truth_path :
        预报场和实况场路径。
        网格 ``.nc`` 或站点 ``.csv``（二者类型须一致）。
    n_probability_bins :
        概率箱个数（含可选的单点 0/1 箱）。
    single_value_lower_limit / single_value_upper_limit :
        是否在 0 / 1 处增加单点概率箱。
    aggregate_coords :
        构造可靠性表时一并求和的坐标，如网格 ``["lat", "lon"]`` 或站点 ``["id"]``；
        ``None`` 表示不聚合。
    output_path :
        若给出则写出结果（网格 nc / 站点 csv）；``None`` 只返回。

    返回
    -------
    xr.Dataset 或 pd.DataFrame
        网格三变量表或站点可靠性长表。
    """
    from probability_reliability_correction.cli.io import read_forecast_or_truth, write_result
    from probability_reliability_correction.src.reliability_calibration import (
        ConstructReliabilityCalibrationTables,
    )

    forecast = read_forecast_or_truth(forecast_path)
    truth = read_forecast_or_truth(truth_path)
    result = ConstructReliabilityCalibrationTables(
        n_probability_bins=n_probability_bins,
        single_value_lower_limit=single_value_lower_limit,
        single_value_upper_limit=single_value_upper_limit,
    ).process(
        forecast,
        truth,
        aggregate_coords=None if aggregate_coords is None else list(aggregate_coords),
    )
    if output_path is not None:
        write_result(result, output_path)
    return result


