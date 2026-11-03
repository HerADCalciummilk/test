#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""估计站点高差订正因子（EstimateDzRescaling）示例脚本。

用法：在仓库根目录修改下方路径后执行::

    python station_height_difference_correction/cli/dsc_estimate_dz_rescaling.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd


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
    similar_altitude: bool = False,
) -> pd.DataFrame:
    """从 CSV 读入站点表，估计 scaled_vertical_displacement 并可选写出。

    使用 ``read_stadata_from_csv`` 读入（兼容普通 CSV 与 attrs 头 CSV）；
    ``drop_same_id=False`` 保留同站多时效/百分位行。
    写出使用 ``write_stadata_to_csv``（meb 标准 attrs 头格式）。
    """
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


if __name__ == "__main__":
    import sys

    # 添加仓库根目录到 sys.path，保证可直接运行示例脚本
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    data_root = (
        Path(__file__).resolve().parent.parent / "test_data" / "estimate-dz-rescaling"
    )
    forecast_file = data_root / "cli_input" / "T1200Z_forecast.csv"
    truth_file = data_root / "cli_input" / "T1200Z_truth.csv"
    neighbour_file = data_root / "cli_input" / "neighbour.csv"
    output_path = data_root / "cli_output" / "scaled_vertical_displacement_T1200Z.csv"
    if not (
        forecast_file.is_file() and truth_file.is_file() and neighbour_file.is_file()
    ):
        print(
            f"示例输入不存在：{data_root / 'cli_input'}\n"
            "请补齐 test_data 后再试，或在此处改成你自己的站点表路径。"
        )
    else:
        process(
            forecast_file,
            truth_file,
            neighbour_file,
            forecast_period=6,
            forecast_data_name="wind_speed",
            dz_lower_bound=-550,
            dz_upper_bound=550,
            land_constraint=True,
            output_path=output_path,
        )
