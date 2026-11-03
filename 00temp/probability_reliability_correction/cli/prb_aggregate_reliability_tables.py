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

import argparse
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

from utils.cli_base import CliBase


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


def _parse_str_list(text: str):
    parts = [part.strip() for part in str(text).split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要至少一个名称，多个用逗号分隔")
    return parts


def _omit_none(kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


_CONFIG_HELP = (
    "运行配置文件，传给 process 的 config。"
    "省略则为 None，process 使用各参数自身的默认值。"
)


class PrbAggregateReliabilityTablesCli(CliBase):
    """聚合可靠性表。``run`` 调用 ``process``。"""

    prog = "python cli/prb_aggregate_reliability_tables.py"
    description = "读取一张或多张可靠性表，按坐标求和聚合并可选写出。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli aggregate --help\n"
        "  python -m cli aggregate --reliability-table-paths PATH --coordinates lat,lon --output-path PATH\n"
        "  python cli/prb_aggregate_reliability_tables.py --reliability-table-paths PATH\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--reliability-table-paths",
            nargs="+",
            required=True,
            metavar="PATH",
            help="可靠性表路径，网格 .nc 或站点 .csv，不可混用。",
        )
        parser.add_argument(
            "--coordinates",
            type=_parse_str_list,
            default=None,
            metavar="NAME[,...]",
            help="要求和的坐标，逗号分隔，如 lat,lon 或 id。省略则为 None。",
        )
        parser.add_argument("--output-path", default=None, metavar="PATH", help="写出路径。省略则只返回。")
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        reliability_table_paths,
        coordinates=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    reliability_table_paths=reliability_table_paths,
                    coordinates=coordinates,
                    output_path=output_path,
                    config=config,
                )
            )
        )
        return 0


def prb_aggregate_reliability_tables_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli aggregate`` 与直接运行本文件都进这里。"""
    return PrbAggregateReliabilityTablesCli().main(argv)


main = prb_aggregate_reliability_tables_cli


if __name__ == "__main__":
    raise SystemExit(prb_aggregate_reliability_tables_cli())
