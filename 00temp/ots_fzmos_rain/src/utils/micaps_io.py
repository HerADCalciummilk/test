from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

import numpy as np

from utils.grid import GridConfig


_NUMBER_PATTERN = re.compile(
    r"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[EeDd][+-]?\d+)?"
)


@dataclass(frozen=True)
class Micaps4Data:
    """MICAPS第4类文件中的网格元数据和数据。"""

    initial_time: datetime
    forecast_hour: int
    level: int
    grid: GridConfig
    values: np.ndarray


def _parse_number(value: str) -> float:
    """兼容 Fortran 常见的 D 指数写法。"""
    return float(value.replace("D", "E").replace("d", "e"))


def read_micaps4(path: str | Path) -> Micaps4Data:
    """读取原程序使用的 MICAPS第4类规则网格文件。"""
    file_path = Path(path)
    with file_path.open("r", encoding="gb18030", errors="replace") as handle:
        first_line = handle.readline()
        header_line = handle.readline()
        data_text = handle.read()

    if not first_line.lower().lstrip().startswith("diamond 4"):
        raise ValueError(f"{file_path} 不是 MICAPS 4 文件")

    header = _NUMBER_PATTERN.findall(header_line)
    if len(header) < 14:
        raise ValueError(f"{file_path} 的网格头字段不足14个")

    year, month, day, hour = map(int, header[:4])
    header_forecast_hour = int(header[4])
    level = int(header[5])
    dlon, dlat, lon_start, lon_end, lat_start, lat_end = map(
        _parse_number, header[6:12]
    )
    num_x, num_y = map(int, header[12:14])
    expected = num_x * num_y
    raw_values = np.fromstring(
        data_text.replace("D", "E").replace("d", "e"),
        dtype=np.float32,
        sep=" ",
    )
    if raw_values.size < expected:
        raw_values = np.asarray(
            [_parse_number(value) for value in _NUMBER_PATTERN.findall(data_text)],
            dtype=np.float32,
        )
    if raw_values.size < expected:
        raise ValueError(
            f"{file_path} 只有 {raw_values.size} 个格点值，预期至少 {expected} 个"
        )

    name_parts = first_line.split()
    forecast_hour = 0
    if name_parts and "_" in name_parts[-1]:
        suffix = name_parts[-1].split("_", 1)[1]
        digits = "".join(character for character in suffix if character.isdigit())
        if len(digits) >= 3:
            forecast_hour = int(digits[:3])
    if forecast_hour == 0:
        forecast_hour = header_forecast_hour

    return Micaps4Data(
        initial_time=datetime(year, month, day, hour),
        forecast_hour=forecast_hour,
        level=level,
        grid=GridConfig(
            lat_start=lat_start,
            lon_start=lon_start,
            lat_end=lat_end,
            lon_end=lon_end,
            dlat=dlat,
            dlon=dlon,
            num_x=num_x,
            num_y=num_y,
        ),
        values=raw_values[:expected].reshape(num_y, num_x),
    )


def write_micaps4(
    path: str | Path,
    initial_time: datetime,
    forecast_hour: int,
    element_name: str,
    grid: GridConfig,
    values: np.ndarray,
) -> None:
    """按原程序的字段宽度和CRLF换行写出 MICAPS第4类文件。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(values, dtype=np.float32)
    expected_shape = (grid.num_y, grid.num_x)
    if array.shape != expected_shape:
        raise ValueError(f"输出网格形状为 {array.shape}，预期为 {expected_shape}")

    date_text = initial_time.strftime("%y%m%d%H")
    first_line = f" diamond 4 {date_text}_{forecast_hour:03d}{element_name}_OTS"
    second_line = (
        f"{initial_time.year:6d}{initial_time.month:6d}{initial_time.day:6d}  "
        f"{initial_time.hour:4d}{forecast_hour:6d}{0:4d}"
        f"{grid.dlon:7.4f}{grid.dlat:7.4f}"
        f"{grid.lon_start:8.3f}{grid.lon_end:8.3f}"
        f"{grid.lat_start:8.3f}{grid.lat_end:8.3f}"
        f"{grid.num_x:5d}{grid.num_y:5d}"
        " 10.000000 0.000000 1000.000000 1.000000 0.000000 "
    )

    with output_path.open("w", encoding="ascii", newline="") as handle:
        handle.write(first_line + "\r\n")
        handle.write(second_line + "\r\n")
        for row in array:
            handle.write("".join(f"{float(value):8.2f}" for value in row))
            handle.write("\r\n")
