#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""估计站点高差订正因子命令行。

在本包目录执行::

    python cli/dsc_estimate_dz_rescaling.py --forecast-path PATH --truth-path PATH --neighbour-path PATH --forecast-period 6 --forecast-data-name wind_speed
    python -m cli.dsc_estimate_dz_rescaling --forecast-path PATH --truth-path PATH --neighbour-path PATH --forecast-period 6 --forecast-data-name wind_speed

Python::

    from cli.dsc_estimate_dz_rescaling import DscEstimateDzRescalingCli
    DscEstimateDzRescalingCli.call(forecast_path="PATH", truth_path="PATH", neighbour_path="PATH", forecast_period=6, forecast_data_name="wind_speed")
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, Union

import pandas as pd


def _bootstrap_paths() -> None:
    """沿用原脚本：把 00temp 放进 sys.path，并让包根上的 utils 优先。"""
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.conf_ini import overlay_none


def process(
    forecast_path: Union[str, Path],
    truth_path: Union[str, Path],
    neighbour_path: Union[str, Path],
    *,
    forecast_period: float,
    forecast_data_name: str,
    truth_data_name: Optional[str] = None,
    output_path: Optional[Union[str, Path]] = None,
    dz_lower_bound: Optional[float] = None,
    dz_upper_bound: Optional[float] = None,
    land_constraint: bool = False,
    similar_altitude: bool = False, config=None) -> pd.DataFrame:
    """从 CSV 读入站点表，估计 scaled_vertical_displacement 并可选写出。

    使用 ``read_stadata_from_csv`` 读入（兼容普通 CSV 与 attrs 头 CSV）；
    ``drop_same_id=False`` 保留同站多时效/百分位行。
    写出使用 ``write_stadata_to_csv``（meb 标准 attrs 头格式）。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "truth_data_name": (truth_data_name, "str"),
        "output_path": (output_path, "str"),
        "dz_lower_bound": (dz_lower_bound, "float"),
        "dz_upper_bound": (dz_upper_bound, "float"),
    })
    truth_data_name = _over['truth_data_name']
    output_path = _over['output_path']
    dz_lower_bound = _over['dz_lower_bound']
    dz_upper_bound = _over['dz_upper_bound']
    from meteva_base import read_stadata_from_csv, write_stadata_to_csv

    from station_height_difference_correction.src.dz_rescaling import EstimateDzRescaling

    forecast = read_stadata_from_csv(str(forecast_path), drop_same_id=False)
    truth = read_stadata_from_csv(str(truth_path), drop_same_id=False)
    neighbour = read_stadata_from_csv(str(neighbour_path), drop_same_id=False)
    if forecast is None or truth is None or neighbour is None:
        raise ValueError("站点 CSV 读取失败，请检查路径与格式")

    plugin = EstimateDzRescaling(
        forecast_period=forecast_period,
        forecast_data_name=forecast_data_name,
        truth_data_name=truth_data_name,
        dz_lower_bound=dz_lower_bound,
        dz_upper_bound=dz_upper_bound,
        land_constraint=land_constraint,
        similar_altitude=similar_altitude,
    )
    result = plugin.process(forecast, truth, neighbour)

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # effective_num 提高小数位，避免订正因子精度被默认 2 位截断
        ok = write_stadata_to_csv(
            result, str(output_path), effective_num=8, creat_dir=True
        )
        if not ok:
            raise RuntimeError(f"写出站点表失败: {output_path}")
    return result


class DscEstimateDzRescalingCli(CliBase):
    """``dsc_estimate_dz_rescaling`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_estimate_dz_rescaling.py"
    description = (
        "估计站点高差订正因子。\n"
        "三份站点表、预报时效和预报字段名必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_estimate_dz_rescaling.py --help\n"
        "  python cli/dsc_estimate_dz_rescaling.py --forecast-path PATH --truth-path PATH "
        "--neighbour-path PATH --forecast-period 6 --forecast-data-name wind_speed "
        "--output-path OUT.csv\n"
        "  python -m cli.dsc_estimate_dz_rescaling --forecast-path PATH --truth-path PATH "
        "--neighbour-path PATH --forecast-period 6 --forecast-data-name wind_speed "
        "--config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--forecast-path", required=True, metavar="PATH", help="预报站点表 CSV。必填。")
        parser.add_argument("--truth-path", required=True, metavar="PATH", help="实况站点表 CSV。必填。")
        parser.add_argument("--neighbour-path", required=True, metavar="PATH", help="邻近站表 CSV。必填。")
        parser.add_argument("--forecast-period", required=True, type=float, help="预报时效。必填。")
        parser.add_argument("--forecast-data-name", required=True, help="预报字段名。必填。")
        parser.add_argument("--truth-data-name", default=None, help="实况字段名。省略则由算法默认。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="订正因子 CSV。省略则不写文件。")
        parser.add_argument("--dz-lower-bound", dest="dz_lower_bound", type=float, default=None, help="高差下限。")
        parser.add_argument("--dz-upper-bound", dest="dz_upper_bound", type=float, default=None, help="高差上限。")
        self.add_optional_bool(parser, "--land-constraint", help_true="启用陆地约束。", help_false="不启用陆地约束。省略则用函数默认值 false。")
        self.add_optional_bool(parser, "--similar-altitude", help_true="只使用相近海拔的邻近站。", help_false="不限制邻近站海拔。省略则用函数默认值 false。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_estimate_dz_rescaling_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_estimate_dz_rescaling`` 都进这里。"""
    return DscEstimateDzRescalingCli().main(argv)


main = dsc_estimate_dz_rescaling_cli


if __name__ == "__main__":
    raise SystemExit(dsc_estimate_dz_rescaling_cli())
