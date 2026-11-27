from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np

from utils.source_reader import SourceField, read_source_field


def read_rain12_from_apcp(
    path_pattern: str,
    initial_time: datetime,
    forecast_hour: int,
    nc_reader: str,
) -> SourceField:
    """从起报后累计降水量计算当前12小时降水量。"""
    end_path = Path(initial_time.strftime(path_pattern).replace("FFF", f"{forecast_hour:03d}"))
    end = read_source_field(end_path, nc_reader=nc_reader)
    if forecast_hour == 12:
        previous_values = np.zeros_like(end.values)
    else:
        previous_hour = forecast_hour - 12
        previous_path = Path(
            initial_time.strftime(path_pattern).replace("FFF", f"{previous_hour:03d}")
        )
        previous = read_source_field(previous_path, nc_reader=nc_reader)
        if previous.grid != end.grid:
            raise ValueError(f"APCP 累计文件网格不一致：{previous_path} 与 {end_path}")
        previous_values = previous.values

    # 输入的9999缺测值不能参与差分；微小或异常负值按无降水处理。
    missing = (~np.isfinite(end.values)) | (~np.isfinite(previous_values))
    missing |= (end.values >= np.float32(9999.0)) | (previous_values >= np.float32(9999.0))
    values = np.maximum(end.values - previous_values, np.float32(0.0)).astype(np.float32)
    values[missing] = np.float32(9999.0)
    return SourceField(values=values, grid=end.grid)
