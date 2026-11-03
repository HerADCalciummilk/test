#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""将官方 Iris 样例预处理为 meb，写入各用例 ``cli_input/``。

Construct 用例的 Iris 源为已沿 ``time`` 拼接的多时效 ``forecast.nc`` /
``truth.nc``（不再使用单时效 ``forecast_0/1``）。验证 Notebook 只读取
``cli_input/``，不在此重复 Iris→meb 转换。

用法（仓库根目录）::

    python probability_reliability_correction/cli/preprocess_test_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Union

import iris
import numpy as np
import pandas as pd
import xarray as xr
import meteva_base as meb

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from probability_reliability_correction.src.utils._reliability import (  # noqa: E402
    reliability_table_from_array,
)

DATA_DIR = PACKAGE_ROOT / "test_data"


def _ensure_meb_default_attrs(da: xr.DataArray) -> xr.DataArray:
    """用 meb.set_griddata_attrs 补齐缺省标准属性（已有值不覆盖）。"""
    meb.set_griddata_attrs(
        da,
        units=da.attrs.get("units"),
        model_var=da.attrs.get("model_var"),
        dtime_units=da.attrs.get("dtime_units"),
        level_type=da.attrs.get("level_type"),
        time_type=da.attrs.get("time_type"),
        time_bounds=da.attrs.get("time_bounds"),
        is_default=True,
    )
    return da


def _with_meb_common_attrs(obj: Union[xr.DataArray, xr.Dataset]):
    """为 Iris→meb 结果补齐 meb 默认 attrs。"""
    out = obj.copy()
    if isinstance(out, xr.DataArray):
        return _ensure_meb_default_attrs(out)
    for name in out.data_vars:
        _ensure_meb_default_attrs(out[name])
    return out


# ---------------------------------------------------------------------------
# Iris → meb 转换
# ---------------------------------------------------------------------------


def _to_ts(coord, index: int = 0) -> pd.Timestamp:
    return pd.Timestamp(str(coord.units.num2date(coord.points[index])))


def _find_threshold_coord(cube):
    for coord in cube.coords():
        if "spp__relative_to_threshold" in coord.attributes:
            return coord
    raise ValueError(f"未找到阈值坐标: {cube.name()}")


def _relative_attr(thr_coord) -> str:
    rel = thr_coord.attributes.get("spp__relative_to_threshold")
    if rel in ("above", "greater_than", "greater_than_or_equal_to", None):
        return "above"
    if rel in ("below", "less_than", "less_than_or_equal_to"):
        return "below"
    return str(rel)


def _spatial_coords(cube):
    if cube.coords("latitude") and cube.coords("longitude"):
        return (
            np.asarray(cube.coord("latitude").points, dtype=np.float32),
            np.asarray(cube.coord("longitude").points, dtype=np.float32),
        )
    return (
        np.asarray(cube.coord(axis="y").points, dtype=np.float32),
        np.asarray(cube.coord(axis="x").points, dtype=np.float32),
    )


def cube_to_meb_prob(cube, *, as_truth: bool = False) -> xr.DataArray:
    """Iris 概率/实况 Cube → meb 六维 DataArray。

    支持单时效 ``(threshold, y, x)`` 与多时效 ``(time, threshold, y, x)``。
    """
    data = cube.data
    if np.ma.isMaskedArray(data):
        arr = np.ma.filled(np.asarray(data, dtype=np.float32), np.nan)
    else:
        arr = np.asarray(data, dtype=np.float32)

    # 多时效：按 time 切片后沿 meb 的 time 维拼接，复用单时效逻辑
    if arr.ndim == 4:
        if not cube.coords("time", dim_coords=True):
            raise ValueError(f"4 维 Cube 缺少 time 维: {cube.name()} {arr.shape}")
        time_dim = cube.coord_dims("time")[0]
        if time_dim != 0:
            raise ValueError(
                f"期望 time 为第 0 维，实际 dim={time_dim}: {cube.name()}"
            )
        pieces = [
            cube_to_meb_prob(cube[i], as_truth=as_truth) for i in range(arr.shape[0])
        ]
        return _with_meb_common_attrs(xr.concat(pieces, dim="time"))

    thr = _find_threshold_coord(cube)
    levels = np.asarray(thr.points, dtype=np.float32)
    lat, lon = _spatial_coords(cube)
    if arr.ndim != 3:
        raise ValueError(f"期望 (threshold, y, x)，实际 {arr.shape}")

    if as_truth and cube.coords("time"):
        frt = _to_ts(cube.coord("time"))
        dtime = 0.0
    else:
        if cube.coords("forecast_reference_time"):
            frt = _to_ts(cube.coord("forecast_reference_time"))
        elif cube.coords("time"):
            frt = _to_ts(cube.coord("time"))
        else:
            frt = pd.Timestamp("2000-01-01")
        if cube.coords("forecast_period"):
            fp = cube.coord("forecast_period")
            dtime = (
                float(fp.points[0] / 3600.0)
                if str(fp.units).startswith("second")
                else float(fp.points[0])
            )
        else:
            dtime = 0.0

    nlev, nlat, nlon = arr.shape
    da = xr.DataArray(
        arr.reshape(1, nlev, 1, 1, nlat, nlon),
        coords={
            "member": [0],
            "level": levels,
            "time": [frt],
            "dtime": [dtime],
            "lat": lat,
            "lon": lon,
        },
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        attrs={
            "units": "1",
            "relative_to_threshold": _relative_attr(thr),
        },
        name=cube.name(),
    )
    return _ensure_meb_default_attrs(da)


def iris_reliability_to_meb(cube) -> xr.Dataset:
    """Iris 可靠性表 Cube → 三变量 meb Dataset。"""
    data = np.ma.filled(np.ma.asarray(cube.data), 0).astype(np.float32)
    if data.ndim == 2:
        data = data.reshape(1, *data.shape, 1, 1)
    elif data.ndim == 3:
        data = data.reshape(*data.shape, 1, 1)
    elif data.ndim != 5:
        raise ValueError(f"不支持的可靠性表形状: {data.shape}")

    thr = None
    for coord in cube.coords():
        if (
            "spp__relative_to_threshold" in coord.attributes
            and coord.ndim == 1
            and coord.shape[0] == data.shape[0]
        ):
            thr = coord
            break
    if thr is None:
        for coord in cube.coords():
            if (
                coord.ndim == 1
                and coord.shape[0] == data.shape[0]
                and coord.name()
                not in (
                    "table_row_index",
                    "probability_bin",
                    "latitude",
                    "longitude",
                    "projection_x_coordinate",
                    "projection_y_coordinate",
                )
            ):
                thr = coord
                break
    levels = (
        np.asarray(thr.points, dtype=np.float32)
        if thr is not None
        else np.array([0.0], dtype=np.float32)
    )

    pbin = cube.coord("probability_bin")
    if pbin.has_bounds():
        bins = np.asarray(pbin.bounds, dtype=np.float32)
    else:
        nbin = data.shape[2]
        edges = np.linspace(0, 1, nbin + 1, dtype=np.float32)
        bins = np.stack([edges[:-1], edges[1:]], axis=1)

    lat, lon = (
        _spatial_coords(cube)
        if (cube.coords(axis="y") and cube.coords(axis="x"))
        else (np.array([0.0], np.float32), np.array([0.0], np.float32))
    )
    if data.shape[-2] != lat.size or data.shape[-1] != lon.size:
        lat = np.array([float(np.mean(lat))], dtype=np.float32)
        lon = np.array([float(np.mean(lon))], dtype=np.float32)

    frt = (
        _to_ts(cube.coord("forecast_reference_time"))
        if cube.coords("forecast_reference_time")
        else pd.Timestamp("2000-01-01")
    )
    time_bounds = None
    if cube.coords("forecast_reference_time"):
        frt_c = cube.coord("forecast_reference_time")
        if frt_c.has_bounds():
            b0, b1 = frt_c.bounds[0]
            time_bounds = (
                pd.Timestamp(str(frt_c.units.num2date(b0))),
                pd.Timestamp(str(frt_c.units.num2date(b1))),
            )
    fp = cube.coord("forecast_period")
    dtime = (
        float(fp.points[0] / 3600.0)
        if str(fp.units).startswith("second")
        else float(fp.points[0])
    )
    return _with_meb_common_attrs(
        reliability_table_from_array(
            data,
            thresholds=levels,
            probability_bins=bins,
            lat=lat,
            lon=lon,
            time_point=frt,
            time_bounds=time_bounds,
            dtime=dtime,
            relative_to_threshold=_relative_attr(thr) if thr is not None else "above",
        )
    )


def save_meb(obj: Union[xr.DataArray, xr.Dataset], path: Path) -> None:
    """写出 meb NetCDF（覆盖已存在文件）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    _with_meb_common_attrs(obj).to_netcdf(tmp)
    try:
        tmp.replace(path)
    except PermissionError as err:
        raise PermissionError(
            f"无法覆盖 {path}（可能被 Jupyter 或其他进程占用）。"
            f"临时文件已写至 {tmp}，请关闭占用后重试。"
        ) from err
    print(f"写入 {path}")


# ---------------------------------------------------------------------------
# 各用例预处理 → cli_input/
# ---------------------------------------------------------------------------


def preprocess_construct() -> None:
    case_dir = DATA_DIR / "construct-reliability-tables" / "basic"
    out = case_dir / "cli_input"
    # Iris 源已是多时效拼接文件，直接转 meb
    save_meb(
        cube_to_meb_prob(iris.load_cube(str(case_dir / "forecast.nc"))),
        out / "forecast.nc",
    )
    save_meb(
        cube_to_meb_prob(
            iris.load_cube(str(case_dir / "truth.nc")), as_truth=True
        ),
        out / "truth.nc",
    )


def preprocess_aggregate() -> None:
    case_dir = DATA_DIR / "aggregate-reliability-tables" / "basic"
    out = case_dir / "cli_input"
    save_meb(
        iris_reliability_to_meb(iris.load_cube(str(case_dir / "reliability_table.nc"))),
        out / "reliability_table.nc",
    )
    save_meb(
        iris_reliability_to_meb(
            iris.load_cube(str(case_dir / "reliability_table_2.nc"))
        ),
        out / "reliability_table_2.nc",
    )


def preprocess_manipulate() -> None:
    case_dir = DATA_DIR / "manipulate-reliability-table" / "basic"
    out = case_dir / "cli_input"
    save_meb(
        iris_reliability_to_meb(
            iris.load_cube(str(case_dir / "reliability_table_cloud.nc"))
        ),
        out / "reliability_table_cloud.nc",
    )
    save_meb(
        iris_reliability_to_meb(
            iris.load_cube(str(case_dir / "reliability_table_precip.nc"))
        ),
        out / "reliability_table_precip.nc",
    )


def preprocess_apply() -> None:
    case_dir = DATA_DIR / "apply-reliability-calibration" / "basic"
    out = case_dir / "cli_input"
    save_meb(
        cube_to_meb_prob(iris.load_cube(str(case_dir / "forecast.nc"))),
        out / "forecast.nc",
    )
    save_meb(
        iris_reliability_to_meb(
            iris.load_cube(str(case_dir / "collapsed_table.nc"))
        ),
        out / "collapsed_table.nc",
    )


def main() -> None:
    if not DATA_DIR.is_dir():
        print(
            f"test_data 目录不存在：{DATA_DIR}\n"
            "请补齐官方样例后再运行预处理。"
        )
        return
    preprocess_construct()
    preprocess_aggregate()
    preprocess_manipulate()
    preprocess_apply()
    print("全部用例 cli_input 预处理完成。")


if __name__ == "__main__":
    main()
