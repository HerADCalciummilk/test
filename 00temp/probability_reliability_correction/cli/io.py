#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""CLI 读写辅助：网格 NetCDF 与站点 csv（meb 表头 attrs 格式）。

``process`` 只调用本模块的统一读/写接口；后缀决定网格或站点：
``.nc`` → ``xarray``；``.csv`` → ``pandas.DataFrame``（meb
``write_stadata_to_csv`` 风格表头，并完整恢复自定义 attrs）。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
import xarray as xr

import meteva_base as meb

from probability_reliability_correction.src.utils._reliability import validate_reliability_table_meb
from probability_reliability_correction.src.utils._station import (
    ensure_sta_data,
    validate_reliability_table_sta,
)

PathLike = Union[str, Path]
GridOrStaField = Union[xr.DataArray, pd.DataFrame]
ReliabilityAny = Union[xr.Dataset, pd.DataFrame]
ReliabilityMany = Union[
    xr.Dataset,
    pd.DataFrame,
    List[xr.Dataset],
    List[pd.DataFrame],
]

_STA_SUFFIXES = {".csv"}
_GRID_SUFFIXES = {".nc"}
_ATTRS_TITLE = "attrs,values"


def _suffix(path: PathLike) -> str:
    return Path(path).suffix.lower()


def is_station_path(path: PathLike) -> bool:
    """路径是否按站点 csv 处理。"""
    return _suffix(path) in _STA_SUFFIXES


def is_grid_path(path: PathLike) -> bool:
    """路径是否按网格 NetCDF 处理。"""
    return _suffix(path) in _GRID_SUFFIXES


def _coerce_attr_value(key: str, value: str) -> Any:
    """将表头字符串还原为常用 Python 类型。"""
    text = str(value).strip()
    if key in ("time_bound_lower", "time_bound_upper"):
        return pd.Timestamp(text)
    if key == "time_bounds":
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)) and len(parsed) == 2:
                return [parsed[0], parsed[1]]
        except (SyntaxError, ValueError):
            pass
        return text
    if text.lower() in ("none", "null"):
        return None
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return float(text)
    except ValueError:
        return text


def _parse_sta_csv_attr_block(path: Path, sep: str = ",") -> tuple[dict, int]:
    """解析 meb 风格表头，返回 ``(attrs, skiprows)``。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines or lines[0].strip() != _ATTRS_TITLE:
        return {}, 0
    attrs: dict = {}
    i = 1
    while i < len(lines):
        line = lines[i].rstrip("\n")
        first = line.split(sep, 1)[0].strip().strip('"')
        # 数据区表头以 level 起头
        if first == "level":
            break
        if not line.strip():
            i += 1
            continue
        key, _, rest = line.partition(sep)
        raw = rest.strip()
        if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            raw = raw[1:-1]
        key = key.strip()
        attrs[key] = _coerce_attr_value(key, raw)
        i += 1
    return attrs, i


def read_sta_dataframe(path: PathLike, *, reliability: bool = False) -> pd.DataFrame:
    """读取 meb 站点 csv（含表头 attrs；完整恢复自定义属性）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    attrs, skiprows = _parse_sta_csv_attr_block(path)
    df = pd.read_csv(path, skiprows=skiprows)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    df.attrs = dict(attrs)
    if reliability:
        # 长表含额外箱列，仅做列/attrs 校验
        validate_reliability_table_sta(df)
        return df
    return ensure_sta_data(df)


def write_sta_dataframe(df: pd.DataFrame, path: PathLike) -> None:
    """写出 meb 站点 csv（表头写入全部 ``DataFrame.attrs``）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from meteva_base.io.write_stadata import write_stadata_to_csv
    except ImportError as err:  # pragma: no cover
        raise ImportError(
            "写出站点 csv 需要 meteva_base.write_stadata_to_csv"
        ) from err
    ok = write_stadata_to_csv(df, str(path), creat_dir=True)
    if not ok:
        raise RuntimeError(f"write_stadata_to_csv 失败: {path}")


def read_meb_dataarray(path: PathLike) -> xr.DataArray:
    """读取预处理后的 meb 六维概率/实况场。"""
    da = xr.open_dataarray(path)
    return meb.checkout_griddata(da, valid_val=(-np.inf, np.inf, np.nan))


def write_meb_dataarray(da: xr.DataArray, path: PathLike) -> None:
    """写出 meb 六维 DataArray。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    da.to_netcdf(path)


def read_reliability_table(path: PathLike) -> xr.Dataset:
    """读取一张 meb 三变量可靠性表（网格）。"""
    ds = xr.open_dataset(path)
    validate_reliability_table_meb(ds)
    return ds


def read_reliability_tables(paths: Sequence[PathLike]) -> List[xr.Dataset]:
    """读取多张网格可靠性表。"""
    return [read_reliability_table(p) for p in paths]


def write_reliability_table(ds: xr.Dataset, path: PathLike) -> None:
    """写出一张可靠性表 Dataset。"""
    validate_reliability_table_meb(ds)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    ds.to_netcdf(path)


def write_reliability_table_list(
    tables: Sequence[xr.Dataset], output_dir: PathLike
) -> List[Path]:
    """按阈值写出 Manipulate 网格结果列表，返回写出路径。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for ds in tables:
        validate_reliability_table_meb(ds)
        lev = float(np.asarray(ds["level"].values).reshape(-1)[0])
        out = output_dir / f"reliability_table_level_{lev:g}.nc"
        if out.exists():
            out.unlink()
        ds.to_netcdf(out)
        written.append(out)
    return written


def read_forecast_or_truth(path: PathLike) -> GridOrStaField:
    """读取预报/实况：``.nc`` → DataArray；``.csv`` → 站点 DataFrame。"""
    path = Path(path)
    if is_station_path(path):
        return read_sta_dataframe(path, reliability=False)
    if is_grid_path(path):
        return read_meb_dataarray(path)
    raise ValueError(f"不支持的预报/实况后缀: {path.suffix}（期望 .nc 或 .csv）")


def read_reliability(path: PathLike) -> ReliabilityAny:
    """读取一张可靠性表：``.nc`` → Dataset；``.csv`` → 站点长表。"""
    path = Path(path)
    if is_station_path(path):
        return read_sta_dataframe(path, reliability=True)
    if is_grid_path(path):
        return read_reliability_table(path)
    raise ValueError(f"不支持的可靠性表后缀: {path.suffix}（期望 .nc 或 .csv）")


def read_reliabilities(paths: Sequence[PathLike]) -> ReliabilityMany:
    """读取一张或多张可靠性表；多表时类型须一致，单表时解包为单个对象。"""
    if not paths:
        raise ValueError("reliability 路径列表为空")
    items = [read_reliability(p) for p in paths]
    kinds = {("sta" if isinstance(t, pd.DataFrame) else "grid") for t in items}
    if len(kinds) > 1:
        raise TypeError("多表读取不可混用网格 Dataset 与站点 DataFrame")
    if len(items) == 1:
        return items[0]
    return items  # type: ignore[return-value]


def write_result(
    obj: Any,
    path: PathLike,
) -> Optional[List[Path]]:
    """按结果类型写出。

    - ``xr.DataArray`` / ``xr.Dataset`` / ``DataFrame`` → 单个文件路径
    - ``list[xr.Dataset]``（Manipulate 网格）→ ``path`` 视为**目录**，返回写出路径列表
    """
    path = Path(path)
    if isinstance(obj, list):
        if not obj:
            raise ValueError("空列表无法写出")
        if all(isinstance(x, xr.Dataset) for x in obj):
            return write_reliability_table_list(obj, path)
        raise TypeError(f"不支持的列表元素类型: {type(obj[0])}")
    if isinstance(obj, xr.DataArray):
        write_meb_dataarray(obj, path)
        return None
    if isinstance(obj, xr.Dataset):
        write_reliability_table(obj, path)
        return None
    if isinstance(obj, pd.DataFrame):
        write_sta_dataframe(obj, path)
        return None
    raise TypeError(f"不支持写出的结果类型: {type(obj)}")
