from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path

import numpy as np


def read_station_codes(path: Path, station_count: int) -> list[str]:
    """读取站点文件中的站号，并用它固定 CSV 转矩阵时的列顺序。"""
    codes: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if parts:
            codes.append(parts[0])
        if len(codes) == station_count:
            break

    if len(codes) != station_count:
        raise ValueError(f"{path} contains {len(codes)} stations, expected {station_count}")
    return codes


def read_csv_matrix(path: Path, station_codes: list[str], rows: int = 732) -> np.ndarray:
    """把 data_nimm 的长表 CSV 转换成原程序使用的 rows x stations 矩阵。"""
    station_index = {code: index for index, code in enumerate(station_codes)}
    by_time: OrderedDict[str, np.ndarray] = OrderedDict()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_columns = {"time", "id", "data0"}
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            missing_text = ", ".join(sorted(missing_columns))
            raise ValueError(f"{path} is missing required columns: {missing_text}")

        for row in reader:
            station_id = row["id"].strip()
            if station_id not in station_index:
                continue

            time_key = row["time"].strip()
            if time_key not in by_time:
                # Fortran 的默认 REAL 为单精度，输入矩阵保持 float32 才能复现阈值边界比较。
                by_time[time_key] = np.full(len(station_codes), np.nan, dtype=np.float32)

            value_text = row["data0"].strip()
            by_time[time_key][station_index[station_id]] = float(value_text) if value_text else np.nan

    if len(by_time) < rows:
        raise ValueError(f"{path} contains {len(by_time)} times, expected at least {rows}")

    matrix = np.vstack(list(by_time.values())[:rows])
    missing_count = int(np.isnan(matrix).sum())
    if missing_count:
        raise ValueError(f"{path} has {missing_count} missing station values in the first {rows} times")

    return matrix


def read_input_data(
    obs_dir: Path,
    ec_dir: Path,
    station_file: Path,
    station_count: int,
    this_year: int,
) -> tuple[list[str], dict[int, np.ndarray], dict[int, np.ndarray]]:
    """按 data_nimm CSV 命名规则读取目标年及前三年的 EC 预报和实况数据。"""
    station_codes = read_station_codes(station_file, station_count)
    years = range(this_year - 3, this_year + 1)

    ec_by_year = {
        year: np.empty((20, 732, station_count), dtype=np.float32)
        for year in years
    }
    for fh_index in range(1, 21):
        fh_text = f"{fh_index * 12:03d}"
        for year in years:
            path = ec_dir / f"ec_{year:04d}_{fh_text}.csv"
            ec_by_year[year][fh_index - 1, :, :] = read_csv_matrix(path, station_codes)

    obs_by_year: dict[int, np.ndarray] = {}
    for year in years:
        path = obs_dir / f"aws_{year:04d}.csv"
        obs_by_year[year] = read_csv_matrix(path, station_codes)

    return station_codes, ec_by_year, obs_by_year


def read_thresholds(path) -> np.ndarray:
    """读取20个预报时效、10个等级的 OTS 映射阈值。"""
    values = np.fromfile(path, dtype=np.float32, sep=" ")
    if values.size != 200:
        raise ValueError(f"{path} 包含 {values.size} 个阈值，预期为 200 个")
    return values.reshape(20, 10)


def write_thresholds(path: Path, thresholds: np.ndarray) -> None:
    """按照每个数值宽 7 位、保留 1 位小数的格式写出 fjyz.txt。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in thresholds:
            handle.write("".join(f"{value:7.1f}" for value in row))
            handle.write("\n")
