#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI：调用 ApplyBiasCorrection 施加简单加性偏差订正。

输入为预处理后的 meb 六维 ``.nc``：一个当前预报，以及零个或多个偏差场
（变量名含 ``forecast_error``）。

在本包目录执行::

    python -m cli.prb_bias_correction --forecast-path fcst.nc --bias-paths bias.nc --output-path corrected.nc
    python cli/prb_bias_correction.py --forecast-path fcst.nc --bias-paths bias.nc --output-path corrected.nc

Python::

    from cli.prb_bias_correction import PrbBiasCorrectionCli
    PrbBiasCorrectionCli.call(
        forecast_path="fcst.nc",
        bias_paths=["bias.nc"],
        output_path="corrected.nc",
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


def _set_kwargs(**kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


def process(
    forecast_path: Union[str, Path],
    bias_paths: Optional[Union[str, Path, Sequence[Union[str, Path]]]] = None,
    *,
    lower_bound: Optional[float] = None,
    upper_bound: Optional[float] = None,
    fill_masked_bias_values: bool = False,
    output_path: Optional[Union[str, Path]] = None,
    config=None,
) -> xr.DataArray:
    """读取预报与偏差场，输出订正结果并可选写出。

    参数
    ----------
    forecast_path :
        待订正预报网格数据。
    bias_paths :
        一个或多个偏差场网格数据；``None`` 或空列表时不订正（告警后返回原预报）。
    lower_bound / upper_bound :
        订正后物理上下界；``None`` 表示该侧不裁剪。
    fill_masked_bias_values :
        偏差缺测是否在相减前填 0。
    output_path :
        若给出则写出结果；``None`` 只返回。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        订正后的预报。
    """
    from simple_bias_correction.src.simple_bias_correction import ApplyBiasCorrection

    # 避免 meb 默认合理值范围误伤风速等诊断量
    valid_val = (-np.inf, np.inf, np.nan)

    forecast = meb.read_griddata_from_nc(str(forecast_path))
    if forecast is None:
        raise ValueError(f"读取网格数据失败: {forecast_path}")
    # 统一维序 member,level,time,dtime,lat,lon 并校验六维格式
    forecast = meb.checkout_griddata(forecast, valid_val=valid_val)

    # 第一个场为待订正预报；后续为偏差场（变量名含 forecast_error，由插件拆分）
    inputs: list[xr.DataArray] = [forecast]
    if bias_paths:
        if isinstance(bias_paths, (str, Path)):
            bias_path_list = [Path(bias_paths)]
        else:
            bias_path_list = [Path(p) for p in bias_paths]
        for path in bias_path_list:
            bias = meb.read_griddata_from_nc(str(path))
            if bias is None:
                raise ValueError(f"读取网格数据失败: {path}")
            inputs.append(meb.checkout_griddata(bias, valid_val=valid_val))

    # 多份偏差时插件沿 time 求平均；无偏差时告警并返回原预报
    result = ApplyBiasCorrection(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        fill_masked_bias_values=fill_masked_bias_values,
    ).process(*inputs)

    if output_path is not None:
        # meb.write_griddata_to_nc 的 effectiveNum 量化会损失精度，改用 xarray 直写。
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        var_name = result.name if result.name else "bias_corrected"
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


class PrbBiasCorrectionCli(CliBase):
    """对预报场施加简单加性偏差订正。"""

    prog = "python -m cli.prb_bias_correction"
    description = (
        "对当前预报施加简单加性偏差订正。\n"
        "偏差场可省略；省略时告警并返回原预报。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.prb_bias_correction --help\n"
        "  python -m cli.prb_bias_correction "
        "--forecast-path fcst.nc --bias-paths bias.nc --output-path corrected.nc\n"
        "  python cli/prb_bias_correction.py "
        "--forecast-path fcst.nc --bias-paths bias.nc --lower-bound 0 --output-path corrected.nc\n"
        "\n"
        "说明:\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--forecast-path",
            dest="forecast_path",
            required=True,
            metavar="PATH",
            help="待订正预报 nc。",
        )
        parser.add_argument(
            "--bias-paths",
            dest="bias_paths",
            nargs="*",
            default=None,
            metavar="PATH",
            help="偏差场 nc，可多个。省略则不订正。",
        )
        parser.add_argument(
            "--lower-bound",
            dest="lower_bound",
            type=float,
            default=None,
            metavar="FLOAT",
            help="订正后物理下界。省略则该侧不裁剪。",
        )
        parser.add_argument(
            "--upper-bound",
            dest="upper_bound",
            type=float,
            default=None,
            metavar="FLOAT",
            help="订正后物理上界。省略则该侧不裁剪。",
        )
        CliBase.add_optional_bool(
            parser,
            "--fill-masked-bias-values",
            dest="fill_masked_bias_values",
            help_true="偏差缺测在相减前填 0。",
            help_false="偏差缺测不填 0。省略时 process 默认为 False。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="订正结果输出 nc。省略则只返回、不写文件。",
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
        forecast_path=None,
        bias_paths=None,
        lower_bound=None,
        upper_bound=None,
        fill_masked_bias_values=None,
        output_path=None,
        config=None,
    ) -> int:
        process(
            forecast_path,
            bias_paths=bias_paths,
            output_path=output_path,
            config=config,
            **_set_kwargs(
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                fill_masked_bias_values=fill_masked_bias_values,
            ),
        )
        return 0


def prb_bias_correction_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.prb_bias_correction`` 与直接运行本文件都进这里。"""
    return PrbBiasCorrectionCli().main(argv)


main = prb_bias_correction_cli


if __name__ == "__main__":
    raise SystemExit(prb_bias_correction_cli())
