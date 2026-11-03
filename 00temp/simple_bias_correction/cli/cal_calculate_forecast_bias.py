#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI：调用 CalculateForecastBias 计算历史平均偏差。

输入为预处理后的 meb 六维 ``.nc``；历史预报与实况可各传多个文件，沿 ``time`` 拼接。
预报与实况须已对齐到同一水平网格。

在本包目录执行::

    python -m cli.cal_calculate_forecast_bias --historic-forecast-paths fcst.nc --truth-paths obs.nc --output-path bias.nc
    python cli/cal_calculate_forecast_bias.py --historic-forecast-paths fcst.nc --truth-paths obs.nc --output-path bias.nc

Python::

    from cli.cal_calculate_forecast_bias import CalCalculateForecastBiasCli
    CalCalculateForecastBiasCli.call(
        historic_forecast_paths=["fcst.nc"],
        truth_paths=["obs.nc"],
        output_path="bias.nc",
    )
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Union

import meteva_base as meb
import numpy as np
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def process(
    historic_forecast_paths: Union[str, Path, Sequence[Union[str, Path]]],
    truth_paths: Union[str, Path, Sequence[Union[str, Path]]],
    *,
    output_path: Optional[Union[str, Path]] = None,
    config=None,
) -> xr.DataArray:
    """读取历史预报与实况，输出空间偏差场并可选写出。

    参数
    ----------
    historic_forecast_paths :
        一个或多个历史单值预报网格数据；多文件时沿 ``time``  维度拼接。
    truth_paths :
        对应实况网格数据；须能与预报按有效时刻配对。
    output_path :
        若给出则写出偏差场；``None`` 只返回结果。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        偏差场，输出变量名为 ``forecast_error_of_<name>``。
    """
    from simple_bias_correction.src.simple_bias_correction import (
        CalculateForecastBias,
    )

    # 风速等诊断量可能超出 meb 默认 [-1000, 1000]；超界格点 checkout 会置 NaN
    valid_val = (-np.inf, np.inf, np.nan)

    def _concat_along_time(
        paths: Union[str, Path, Sequence[Union[str, Path]]],
    ) -> xr.DataArray:
        """将多个单日 meb 文件拼成带历史 ``time`` 维的六维场。"""
        if isinstance(paths, (str, Path)):
            path_list = [Path(paths)]
        else:
            path_list = [Path(p) for p in paths]
        if not path_list:
            raise ValueError("至少需要一个输入文件路径。")

        pieces: list[xr.DataArray] = []
        for path in path_list:
            da = meb.read_griddata_from_nc(str(path))
            if da is None:
                raise ValueError(f"读取网格数据失败: {path}")
            # 统一维序 member,level,time,dtime,lat,lon 并校验六维格式
            pieces.append(meb.checkout_griddata(da, valid_val=valid_val))

        if len(pieces) == 1:
            return pieces[0]
        # 各文件 time 仅含一个起报点；拼接后 time 维即多日历史样本
        return xr.concat(pieces, dim="time", coords="different", compat="equals")

    # 预报与实况分别拼接，再由 CalculateForecastBias 按有效时刻配对
    historic_forecasts = _concat_along_time(historic_forecast_paths)
    truths = _concat_along_time(truth_paths)
    result = CalculateForecastBias().process(historic_forecasts, truths)

    if output_path is not None:
        # meb.write_griddata_to_nc 的 effectiveNum 量化会损失精度，改用 xarray 直写。
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name
        result.to_dataset(name=var_name).to_netcdf(
            out_path,
            mode="w",
            encoding={
                var_name: {
                    "dtype": "float32",
                    "_FillValue": np.float32(np.nan),
                }
            },
        )

    return result


class CalCalculateForecastBiasCli(CliBase):
    """计算历史预报相对实况的平均偏差场。"""

    prog = "python -m cli.cal_calculate_forecast_bias"
    description = (
        "计算历史预报相对实况的平均偏差场。\n"
        "历史预报与实况各可传多个 nc，沿 time 拼接。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.cal_calculate_forecast_bias --help\n"
        "  python -m cli.cal_calculate_forecast_bias "
        "--historic-forecast-paths fcst.nc --truth-paths obs.nc --output-path bias.nc\n"
        "  python cli/cal_calculate_forecast_bias.py "
        "--historic-forecast-paths fcst.nc --truth-paths obs.nc --output-path bias.nc\n"
        "\n"
        "说明:\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--historic-forecast-paths",
            dest="historic_forecast_paths",
            nargs="+",
            required=True,
            metavar="PATH",
            help="历史预报 nc，可多个，沿 time 拼接。",
        )
        parser.add_argument(
            "--truth-paths",
            dest="truth_paths",
            nargs="+",
            required=True,
            metavar="PATH",
            help="实况 nc，可多个，须能与预报按有效时刻配对。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="偏差场输出 nc。省略则只返回、不写文件。",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置文件，传给 process 的 config。"
                "相对路径按项目根解析。"
                "本模块无 ini 读取器，省略则不改路径。"
            ),
        )

    def run(
        self,
        historic_forecast_paths=None,
        truth_paths=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            historic_forecast_paths,
            truth_paths,
            output_path=output_path,
            config=config,
        )
        return 0


def cal_calculate_forecast_bias_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.cal_calculate_forecast_bias`` 与直接运行本文件都进这里。"""
    return CalCalculateForecastBiasCli().main(argv)


main = cal_calculate_forecast_bias_cli


if __name__ == "__main__":
    raise SystemExit(cal_calculate_forecast_bias_cli())
