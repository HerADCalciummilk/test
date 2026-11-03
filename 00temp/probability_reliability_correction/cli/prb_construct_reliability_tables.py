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


class PrbConstructReliabilityTablesCli(CliBase):
    """构建可靠性表。``run`` 调用 ``process``。"""

    prog = "python cli/prb_construct_reliability_tables.py"
    description = (
        "读取预报/实况，构建可靠性表并可选写出。\n"
        "未在命令行给出的可选项保持 process 的默认值。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli construct --help\n"
        "  python -m cli construct --forecast-path PATH --truth-path PATH --output-path PATH\n"
        "  python cli/prb_construct_reliability_tables.py --forecast-path PATH --truth-path PATH\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--forecast-path", required=True, metavar="PATH", help="预报场路径（.nc 或 .csv）。")
        parser.add_argument("--truth-path", required=True, metavar="PATH", help="实况场路径（.nc 或 .csv）。")
        parser.add_argument(
            "--n-probability-bins",
            type=int,
            default=None,
            help="概率箱个数。省略则使用 process 默认值 5。",
        )
        CliBase.add_optional_bool(
            parser,
            "--single-value-lower-limit",
            help_true="在 0 处增加单点概率箱。",
            help_false="不在 0 处增加单点概率箱。省略则使用 process 默认值。",
        )
        CliBase.add_optional_bool(
            parser,
            "--single-value-upper-limit",
            help_true="在 1 处增加单点概率箱。",
            help_false="不在 1 处增加单点概率箱。省略则使用 process 默认值。",
        )
        parser.add_argument(
            "--aggregate-coords",
            type=_parse_str_list,
            default=None,
            metavar="NAME[,...]",
            help="构造时一并求和的坐标，逗号分隔，如 lat,lon。省略则为 None。",
        )
        parser.add_argument("--output-path", default=None, metavar="PATH", help="写出路径。省略则只返回。")
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        forecast_path,
        truth_path,
        n_probability_bins=None,
        single_value_lower_limit=None,
        single_value_upper_limit=None,
        aggregate_coords=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    forecast_path=forecast_path,
                    truth_path=truth_path,
                    n_probability_bins=n_probability_bins,
                    single_value_lower_limit=single_value_lower_limit,
                    single_value_upper_limit=single_value_upper_limit,
                    aggregate_coords=aggregate_coords,
                    output_path=output_path,
                    config=config,
                )
            )
        )
        return 0


def prb_construct_reliability_tables_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli construct`` 与直接运行本文件都进这里。"""
    return PrbConstructReliabilityTablesCli().main(argv)


main = prb_construct_reliability_tables_cli


if __name__ == "__main__":
    raise SystemExit(prb_construct_reliability_tables_cli())
