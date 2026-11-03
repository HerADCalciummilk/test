#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""应用站点高差订正命令行。

在本包目录执行::

    python cli/dsc_apply_dz_rescaling.py --forecast-path PATH --scaled-dz-path PATH --forecast-data-name wind_speed
    python -m cli.dsc_apply_dz_rescaling --forecast-path PATH --scaled-dz-path PATH --forecast-data-name wind_speed

Python::

    from cli.dsc_apply_dz_rescaling import DscApplyDzRescalingCli
    DscApplyDzRescalingCli.call(forecast_path="PATH", scaled_dz_path="PATH", forecast_data_name="wind_speed")
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
    scaled_dz_path: Union[str, Path],
    *,
    forecast_data_name: str,
    output_path: Optional[Union[str, Path]] = None,
    frt_hour_leniency: int = 1, config=None) -> pd.DataFrame:
    """读入站点预报与订正因子，应用 ``forecast *= scaled_vertical_displacement``。

    使用 ``read_stadata_from_csv`` 读入（兼容普通 CSV 与 attrs 头 CSV）；
    ``drop_same_id=False`` 保留同站多时效/百分位行。
    写出使用 ``write_stadata_to_csv``（meb 标准 attrs 头格式）。
    """
    # 只填补仍为 None 的项。默认 resource/conf.ini 为空，不改已传入的参数。
    _over = overlay_none(__file__, config, {
        "output_path": (output_path, "str"),
    })
    output_path = _over['output_path']
    from meteva_base import read_stadata_from_csv, write_stadata_to_csv

    from station_height_difference_correction.src.dz_rescaling import ApplyDzRescaling

    forecast = read_stadata_from_csv(str(forecast_path), drop_same_id=False)
    scaled_dz = read_stadata_from_csv(str(scaled_dz_path), drop_same_id=False)
    if forecast is None or scaled_dz is None:
        raise ValueError("站点 CSV 读取失败，请检查路径与格式")

    plugin = ApplyDzRescaling(
        forecast_data_name=forecast_data_name,
        frt_hour_leniency=frt_hour_leniency,
    )
    result = plugin.process(forecast, scaled_dz)

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        ok = write_stadata_to_csv(
            result, str(output_path), effective_num=8, creat_dir=True
        )
        if not ok:
            raise RuntimeError(f"写出站点表失败: {output_path}")
    return result


class DscApplyDzRescalingCli(CliBase):
    """``dsc_apply_dz_rescaling`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/dsc_apply_dz_rescaling.py"
    description = (
        "应用站点高差订正。\n"
        "预报表、订正因子表和预报字段名必填。省略的可选项保持函数默认值；"
        "仍为 None 的项可从 --config 或 resource/conf.ini 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/dsc_apply_dz_rescaling.py --help\n"
        "  python cli/dsc_apply_dz_rescaling.py --forecast-path PATH --scaled-dz-path PATH "
        "--forecast-data-name wind_speed --output-path OUT.csv\n"
        "  python -m cli.dsc_apply_dz_rescaling --forecast-path PATH --scaled-dz-path PATH "
        "--forecast-data-name wind_speed --config resource/conf.ini\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--forecast-path", required=True, metavar="PATH", help="预报站点表 CSV。必填。")
        parser.add_argument("--scaled-dz-path", required=True, metavar="PATH", help="订正因子站点表 CSV。必填。")
        parser.add_argument("--forecast-data-name", required=True, help="预报字段名。必填。")
        parser.add_argument("--output-path", default=None, metavar="PATH", help="订正后站点表 CSV。省略则不写文件。")
        parser.add_argument("--frt-hour-leniency", dest="frt_hour_leniency", type=int, default=None, help="起报小时容差。省略则用 1。")
        parser.add_argument("--config", default=None, metavar="PATH", help="运行配置 ini，传给 process。相对路径按本包目录解析。省略则用 resource/conf.ini。")

    def run(self, **params) -> int:
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def dsc_apply_dz_rescaling_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。直接运行本文件与 ``python -m cli.dsc_apply_dz_rescaling`` 都进这里。"""
    return DscApplyDzRescalingCli().main(argv)


main = dsc_apply_dz_rescaling_cli


if __name__ == "__main__":
    raise SystemExit(dsc_apply_dz_rescaling_cli())
