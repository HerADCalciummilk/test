#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI 示例：调用 AggregateReliabilityCalibrationTables 聚合可靠性表。

用法（仓库根目录，先改脚本底部路径）::

    python probability_reliability_correction/cli/prb_aggregate_reliability_tables.py

输入由后缀决定：``.nc`` 网格表；``.csv`` 站点长表。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Union

import pandas as pd
import xarray as xr


def process(
    reliability_table_paths: Sequence[Union[str, Path]],
    *,
    coordinates: Optional[Sequence[str]] = None,
    output_path: Optional[Union[str, Path]] = None,
) -> Union[xr.Dataset, pd.DataFrame]:
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


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    import sys

    _PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    cli_input = _PACKAGE_ROOT / "resource" / "cli_input"
    cli_output = _PACKAGE_ROOT / "resource" / "cli_output"
    cli_output.mkdir(parents=True, exist_ok=True)
    process(
        [cli_input / "aggregate_reliability_table.nc"],
        coordinates=["lat", "lon"],
        output_path=cli_output / "mig_cli_collapsed.nc",
    )


if __name__ == "__main__":
    main()
