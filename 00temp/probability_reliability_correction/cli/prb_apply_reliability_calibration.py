#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""应用可靠性订正命令行。

输入由后缀决定：网格 ``.nc``；站点 ``.csv``（预报与表类型须一致）。
站点表为 Manipulate 后的一张长表即可。

在本包目录执行::

    python -m cli apply --forecast-path PATH
    python cli/prb_apply_reliability_calibration.py --forecast-path PATH

Python::

    from cli.prb_apply_reliability_calibration import PrbApplyReliabilityCalibrationCli
    PrbApplyReliabilityCalibrationCli.call(forecast_path="PATH")
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
    reliability_table_paths: Optional[Sequence[Union[str, Path]]] = None,
    *,
    point_by_point: bool = False,
    output_path: Optional[Union[str, Path]] = None, config=None) -> Union[xr.DataArray, pd.DataFrame]:
    """读取概率预报与可靠性表，输出订正结果并可选写出。

    参数
    ----------
    forecast_path :
        待订正场：网格 ``.nc`` 或站点 ``.csv``。
    reliability_table_paths :
        可靠性表路径；网格可为 Manipulate 后的多阈值 nc 列表，站点为单张长表
        csv；``None`` 表示不做订正（原样返回）。
    point_by_point :
        是否按空间点 / 站点分别套用对应表。
    output_path :
        若给出则写出结果；``None`` 只返回。

    返回
    -------
    xr.DataArray 或 pd.DataFrame
        订正后的概率场。
    """
    from probability_reliability_correction.cli.io import (
        read_forecast_or_truth,
        read_reliabilities,
        write_result,
    )
    from probability_reliability_correction.src.reliability_calibration import (
        ApplyReliabilityCalibration,
    )

    forecast = read_forecast_or_truth(forecast_path)
    table_arg = (
        None
        if not reliability_table_paths
        else read_reliabilities(reliability_table_paths)
    )
    result = ApplyReliabilityCalibration(point_by_point=point_by_point).process(
        forecast, table_arg
    )
    if output_path is not None:
        write_result(result, output_path)
    return result


def _omit_none(kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


_CONFIG_HELP = (
    "运行配置文件，传给 process 的 config。"
    "省略则为 None，process 使用各参数自身的默认值。"
)


class PrbApplyReliabilityCalibrationCli(CliBase):
    """应用可靠性订正。``run`` 调用 ``process``。"""

    prog = "python cli/prb_apply_reliability_calibration.py"
    description = "读取概率预报与可靠性表，输出订正结果并可选写出。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli apply --help\n"
        "  python -m cli apply --forecast-path PATH --reliability-table-paths PATH --output-path PATH\n"
        "  python cli/prb_apply_reliability_calibration.py --forecast-path PATH\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--forecast-path", required=True, metavar="PATH", help="待订正场：网格 .nc 或站点 .csv。")
        parser.add_argument(
            "--reliability-table-paths",
            nargs="+",
            default=None,
            metavar="PATH",
            help="可靠性表路径。省略则为 None，表示不做订正。",
        )
        CliBase.add_optional_bool(
            parser,
            "--point-by-point",
            help_true="按空间点或站点分别套用对应表。",
            help_false="全场共用表。省略则使用 process 默认值。",
        )
        parser.add_argument("--output-path", default=None, metavar="PATH", help="写出路径。省略则只返回。")
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        forecast_path,
        reliability_table_paths=None,
        point_by_point=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    forecast_path=forecast_path,
                    reliability_table_paths=reliability_table_paths,
                    point_by_point=point_by_point,
                    output_path=output_path,
                    config=config,
                )
            )
        )
        return 0


def prb_apply_reliability_calibration_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli apply`` 与直接运行本文件都进这里。"""
    return PrbApplyReliabilityCalibrationCli().main(argv)


main = prb_apply_reliability_calibration_cli


if __name__ == "__main__":
    raise SystemExit(prb_apply_reliability_calibration_cli())
