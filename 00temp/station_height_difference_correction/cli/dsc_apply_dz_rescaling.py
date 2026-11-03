#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""应用站点高差订正（ApplyDzRescaling）示例脚本。

用法：在仓库根目录修改下方路径后执行::

    python station_height_difference_correction/cli/dsc_apply_dz_rescaling.py
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd


def process(
    forecast_path: Union[str, Path],
    scaled_dz_path: Union[str, Path],
    *,
    forecast_data_name: str,
    output_path: Optional[Union[str, Path]] = None,
    frt_hour_leniency: int = 1,
) -> pd.DataFrame:
    """读入站点预报与订正因子，应用 ``forecast *= scaled_vertical_displacement``。

    使用 ``read_stadata_from_csv`` 读入（兼容普通 CSV 与 attrs 头 CSV）；
    ``drop_same_id=False`` 保留同站多时效/百分位行。
    写出使用 ``write_stadata_to_csv``（meb 标准 attrs 头格式）。
    """
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


if __name__ == "__main__":
    import sys

    # 添加仓库根目录到 sys.path，保证可直接运行示例脚本
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    data_root = Path(__file__).resolve().parent.parent / "test_data" / "apply-dz-rescaling"
    forecast_file = data_root / "cli_input" / "apply_forecast.csv"
    scaled_dz_file = data_root / "cli_input" / "apply_scaled_dz.csv"
    output_path = data_root / "cli_output" / "forecast_rescaled.csv"
    if not forecast_file.is_file() or not scaled_dz_file.is_file():
        print(
            f"示例输入不存在：{forecast_file} 或 {scaled_dz_file}\n"
            "请补齐 test_data 后再试，或在此处改成你自己的站点表路径。"
        )
    else:
        process(
            forecast_file,
            scaled_dz_file,
            forecast_data_name="wind_speed",
            output_path=output_path,
        )
