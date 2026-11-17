"""读写 meteva 六维格点和站点表。"""

from __future__ import annotations

import contextlib
import io
import locale
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

GRID_DIMS = ("member", "level", "time", "dtime", "lat", "lon")
STATION_COORDS = ("level", "time", "dtime", "id", "lon", "lat")


def lead_units(units) -> str:
    """把 dtime_units 规范成 hour 或 minute。"""
    text = "" if units is None else str(units).strip().strip("\"'").lower()
    if text.startswith("hour") or text in {"h", "hr", "hrs", "hours"}:
        return "hour"
    if text.startswith("min"):
        return "minute"
    if text == "":
        return "hour"
    raise ValueError(f"无法识别的 dtime_units: {units}")


def validity_times(cycle, dtime, units) -> pd.Series:
    """有效时间 = 起报时间 time + 时效 dtime。"""
    unit = "h" if lead_units(units) == "hour" else "min"
    origin = pd.to_datetime(cycle)
    lead = pd.to_timedelta(np.asarray(dtime, dtype=np.float64), unit=unit)
    return pd.to_datetime(origin + lead)


def ensure_grid(data: xr.DataArray) -> xr.DataArray:
    """补齐并排列成 member, level, time, dtime, lat, lon。"""
    if not isinstance(data, xr.DataArray):
        raise TypeError("格点数据需要是 xarray.DataArray")
    missing = [dim for dim in ("lat", "lon") if dim not in data.dims]
    if missing:
        raise ValueError(f"格点数据缺少维度: {missing}")

    grid = data.copy()
    defaults = {
        "member": ["0"],
        "level": [0.0],
        "time": [np.datetime64("1970-01-01T00:00:00")],
        "dtime": [0],
    }
    for dim, value in defaults.items():
        if dim not in grid.dims:
            grid = grid.expand_dims({dim: value})
    grid = grid.transpose(*GRID_DIMS)
    attrs = dict(grid.attrs)
    attrs["dtime_units"] = lead_units(attrs.get("dtime_units", "hour"))
    attrs.setdefault("units", "")
    attrs.setdefault("level_type", "surface")
    attrs.setdefault("time_type", "UT")
    attrs.setdefault("time_bounds", [0, 0])
    attrs.setdefault("model_var", "")
    grid.attrs = attrs
    grid = grid.assign_coords(
        member=[str(item) for item in grid.member.values],
        level=np.asarray(grid.level.values, dtype=np.float32),
        dtime=np.asarray(np.rint(np.asarray(grid.dtime.values, dtype=np.float64)), dtype=np.int32),
        time=pd.to_datetime(grid.time.values).to_numpy(dtype="datetime64[ns]"),
        lat=np.asarray(grid.lat.values, dtype=np.float64),
        lon=np.asarray(grid.lon.values, dtype=np.float64),
    )
    grid.data = np.asarray(grid.data, dtype=np.float32)
    return grid


def ensure_station(frame: pd.DataFrame) -> pd.DataFrame:
    """检查站点表坐标列，并补上 dtime_units。"""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("站点数据需要是 pandas.DataFrame")
    missing = [column for column in STATION_COORDS if column not in frame.columns]
    if missing:
        raise ValueError(f"站点数据缺少列: {missing}")
    station = frame.copy()
    attrs = dict(getattr(frame, "attrs", {}) or {})
    attrs["dtime_units"] = lead_units(attrs.get("dtime_units", "hour"))
    attrs.setdefault("units", "")
    attrs.setdefault("level_type", "surface")
    attrs.setdefault("time_type", "UT")
    attrs.setdefault("model_var", "")
    station.attrs = attrs
    station["time"] = pd.to_datetime(station["time"])
    station["dtime"] = np.rint(station["dtime"].astype(float)).astype(np.int32)
    station["level"] = station["level"].astype(float)
    station["id"] = station["id"].astype(np.int32)
    station["lon"] = station["lon"].astype(float)
    station["lat"] = station["lat"].astype(float)
    return station


def load_grid(path) -> xr.DataArray:
    """用 meteva_base.read_griddata_from_nc 读取格点。"""
    import meteva_base

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    with contextlib.redirect_stdout(io.StringIO()):
        grid = meteva_base.read_griddata_from_nc(str(source))
    if grid is None:
        raise ValueError(f"无法按 meteva 格点格式读取: {source}")
    return ensure_grid(grid)


def load_station(path) -> pd.DataFrame:
    """用 meteva_base.read_stadata_from_csv 读取站点表。

    同一站号会对应多个起报时间、时效和成员，因此关闭按站号去重。
    """
    import meteva_base

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    with contextlib.redirect_stdout(io.StringIO()):
        station = meteva_base.read_stadata_from_csv(
            str(source), drop_same_id=False, show=False
        )
    if station is None:
        raise ValueError(f"无法按 meteva 站点格式读取: {source}")
    return ensure_station(station)


def save_grid(grid: xr.DataArray, path) -> None:
    """经 meteva_base 转成标准格点后再写出 NetCDF。"""
    import meteva_base

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = ensure_grid(grid)
    if data.attrs.get("model_var") and not data.attrs.get("model"):
        data.attrs["model"] = data.attrs["model_var"]
    name = data.name or "data0"
    dataset = data.to_dataset(name=name)
    with contextlib.redirect_stdout(io.StringIO()):
        converted = meteva_base.xarray_to_griddata(dataset, value_name=name)
    for key, value in data.attrs.items():
        converted.attrs.setdefault(key, value)
    if converted.name is None:
        converted = converted.rename(name)
    with contextlib.redirect_stdout(io.StringIO()):
        ok = meteva_base.write_griddata_to_nc(
            converted,
            str(target),
            creat_dir=True,
            effectiveNum=4,
            show=False,
        )
    if not ok:
        raise RuntimeError(f"write_griddata_to_nc 写出失败: {target}")


def save_station(station: pd.DataFrame, path) -> None:
    """写出 read_stadata_from_csv 能读回的站点表。

    该读取函数固定跳过 1 行表头和 6 行属性，所以这里只写这 6 个属性。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame = ensure_station(station)
    body = frame.copy()
    body["time"] = pd.to_datetime(body["time"])
    time_bounds = frame.attrs.get("time_bounds", [0, 0])
    if not isinstance(time_bounds, str):
        time_bounds = str(list(time_bounds))
    attributes = {
        "units": frame.attrs.get("units", ""),
        "model_var": frame.attrs.get("model_var", ""),
        "dtime_units": frame.attrs.get("dtime_units", "hour"),
        "level_type": frame.attrs.get("level_type", "surface"),
        "time_type": frame.attrs.get("time_type", "UT"),
        "time_bounds": time_bounds,
    }
    header = "attrs,values\n" + "".join(
        f'{key},"{value}"\n' for key, value in attributes.items()
    )
    text = header + body.to_csv(index=False, float_format="%.4f")
    target.write_text(text, encoding=locale.getpreferredencoding(False))


def load_meteva(path):
    """按后缀读取格点 nc 或站点 csv。"""
    suffix = Path(path).suffix.lower()
    if suffix in {".nc", ".nc4"}:
        return load_grid(path)
    if suffix == ".csv":
        return load_station(path)
    raise ValueError(f"只支持 .nc 格点或 .csv 站点: {path}")


def save_meteva(data, path) -> None:
    """按数据类型写出格点或站点。"""
    if isinstance(data, xr.DataArray):
        save_grid(data, path)
        return
    if isinstance(data, pd.DataFrame):
        save_station(data, path)
        return
    raise TypeError("只能保存格点 DataArray 或站点 DataFrame")
