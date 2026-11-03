#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI 示例：调用 ManipulateReliabilityTable 整理可靠性表。

用法（仓库根目录，先改脚本底部路径）::

    python probability_reliability_correction/cli/prb_manipulate_reliability_table.py

网格：``output_path`` 为**目录**（按阈值多文件）；站点：为**单个 csv**。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import pandas as pd
import xarray as xr


def process(
    reliability_table_path: Union[str, Path],
    *,
    minimum_forecast_count: int = 200,
    point_by_point: bool = False,
    output_path: Optional[Union[str, Path]] = None,
) -> Union[List[xr.Dataset], pd.DataFrame]:
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


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    import sys

    _PACKAGE_ROOT = Path(__file__).resolve().parents[1]
    repo_root = str(_PACKAGE_ROOT.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    cli_input = _PACKAGE_ROOT / "resource" / "cli_input"
    cli_output = _PACKAGE_ROOT / "resource" / "cli_output" / "mig_cli_cloud_min300"
    cli_output.mkdir(parents=True, exist_ok=True)
    process(
        cli_input / "manipulate_reliability_table.nc",
        minimum_forecast_count=300,
        point_by_point=False,
        output_path=cli_output,
    )


if __name__ == "__main__":
    main()
