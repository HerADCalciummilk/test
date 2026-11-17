"""格点、站点表与分位数回归森林内部表格之间的转换。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from quantile_regression_random_forest.util.meteva_data import ensure_grid, ensure_station, lead_units, validity_times

HELPER_COLUMNS = {
    "forecast_reference_time",
    "forecast_period",
    "valid_time",
    "level",
    "time",
    "dtime",
    "id",
    "lon",
    "lat",
    "member",
    "percentile",
    "realization",
}


def value_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if column not in HELPER_COLUMNS]


def grid_to_frame(grid: xr.DataArray, variable_name: str | None = None) -> pd.DataFrame:
    grid = ensure_grid(grid)
    name = variable_name or grid.name or "data0"
    values = grid.copy()
    values.name = name
    frame = values.to_dataframe(name=name).reset_index()
    units = lead_units(grid.attrs.get("dtime_units", "hour"))
    frame["forecast_reference_time"] = pd.to_datetime(frame["time"])
    frame["forecast_period"] = frame["dtime"].astype(np.int64)
    frame["valid_time"] = validity_times(
        frame["forecast_reference_time"], frame["forecast_period"], units
    )
    frame["lat"] = np.round(frame["lat"].astype(float), 5)
    frame["lon"] = np.round(frame["lon"].astype(float), 5)
    frame.attrs["source_kind"] = "grid"
    frame.attrs["dtime_units"] = units
    frame.attrs["grid_attrs"] = dict(grid.attrs)
    return frame


def station_to_frame(station: pd.DataFrame) -> pd.DataFrame:
    station = ensure_station(station)
    frame = station.copy()
    units = lead_units(station.attrs.get("dtime_units", "hour"))
    frame["forecast_reference_time"] = pd.to_datetime(frame["time"])
    frame["forecast_period"] = frame["dtime"].astype(np.int64)
    frame["valid_time"] = validity_times(
        frame["forecast_reference_time"], frame["forecast_period"], units
    )
    frame["lat"] = np.round(frame["lat"].astype(float), 5)
    frame["lon"] = np.round(frame["lon"].astype(float), 5)
    frame.attrs["source_kind"] = "station"
    frame.attrs["dtime_units"] = units
    frame.attrs["station_attrs"] = dict(station.attrs)
    return frame


def as_forecast_frame(data, variable_name: str | None = None) -> pd.DataFrame:
    if isinstance(data, xr.DataArray):
        return grid_to_frame(data, variable_name)
    if isinstance(data, pd.DataFrame):
        return station_to_frame(data)
    raise TypeError("预报需要是格点 DataArray 或站点 DataFrame")


def combine_forecasts(forecasts, variable_names: list[str] | None = None) -> pd.DataFrame:
    """合并主预报和额外预报因子。静态场只有一个成员时按站点或格点对齐。"""
    if not isinstance(forecasts, (list, tuple)):
        forecasts = [forecasts]
    if variable_names is not None and len(variable_names) != len(forecasts):
        raise ValueError("变量名数量需要和预报数据数量一致")

    frames = []
    for index, item in enumerate(forecasts):
        name = None if variable_names is None else variable_names[index]
        frames.append(as_forecast_frame(item, name))
    kind = frames[0].attrs["source_kind"]
    if any(frame.attrs["source_kind"] != kind for frame in frames):
        raise ValueError("格点预报和站点预报不能混在同一次订正里")

    base = frames[0]
    for extra in frames[1:]:
        base = _merge_feature_frame(base, extra)
    if not any(column in base.columns for column in ("member", "realization", "percentile")):
        base["member"] = 0
    base.attrs["source_kind"] = kind
    base.attrs["dtime_units"] = frames[0].attrs["dtime_units"]
    base.attrs["grid_attrs"] = frames[0].attrs.get("grid_attrs", {})
    base.attrs["station_attrs"] = frames[0].attrs.get("station_attrs", {})
    return base


def _merge_feature_frame(base: pd.DataFrame, extra: pd.DataFrame) -> pd.DataFrame:
    extra_values = [column for column in value_columns(extra) if column not in base.columns]
    if not extra_values:
        return base
    keys = [
        column
        for column in ("level", "forecast_reference_time", "forecast_period", "valid_time", "id", "lat", "lon")
        if column in base.columns and column in extra.columns
    ]
    extra_member = "member" in extra.columns and extra["member"].nunique(dropna=False) > 1
    base_member = "member" in base.columns and base["member"].nunique(dropna=False) > 1
    if extra_member and base_member:
        keys.append("member")
    table = extra[keys + extra_values].drop_duplicates()
    merged = base.merge(table, on=keys, how="left")
    merged.attrs = dict(base.attrs)
    return merged


def as_truth_frame(data, column: str | None = None) -> pd.DataFrame:
    if isinstance(data, xr.DataArray):
        name = column or data.name or "ob_value"
        frame = grid_to_frame(data, name)
        source_column = name
    elif isinstance(data, pd.DataFrame):
        frame = station_to_frame(data)
        if column is not None:
            source_column = column
        elif "ob_value" in frame.columns:
            source_column = "ob_value"
        else:
            columns = value_columns(frame)
            if len(columns) != 1:
                raise ValueError(f"实况有多列数据，请指定列名，当前列为 {columns}")
            source_column = columns[0]
    else:
        raise TypeError("实况需要是格点 DataArray 或站点 DataFrame")
    if source_column not in frame.columns:
        raise ValueError(f"实况数据中没有列 {source_column}")
    frame = frame.rename(columns={source_column: "ob_value"})
    return frame


def default_site_keys(frame: pd.DataFrame) -> list[str]:
    if "id" in frame.columns:
        return ["id"]
    return ["lat", "lon"]


def group_keys(frame: pd.DataFrame, site_keys: list[str]) -> list[str]:
    keys = ["forecast_reference_time", "forecast_period"]
    if "level" in frame.columns:
        keys.append("level")
    keys.extend(site_keys)
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        raise ValueError(f"无法按这些列分组: {missing}")
    return keys


def predictions_to_grid(
    template: pd.DataFrame,
    values: np.ndarray,
    quantiles: list[float],
    variable_name: str,
    attrs: dict,
) -> xr.DataArray:
    pieces = []
    for index, quantile in enumerate(quantiles):
        part = template[["level", "time", "dtime", "lat", "lon"]].copy()
        part["member"] = _quantile_label(quantile)
        part[variable_name] = np.asarray(values[:, index], dtype=np.float32)
        pieces.append(part)
    table = pd.concat(pieces, ignore_index=True)
    table["time"] = pd.to_datetime(table["time"])
    grid = table.set_index(["member", "level", "time", "dtime", "lat", "lon"])[variable_name].to_xarray()
    grid = grid.transpose("member", "level", "time", "dtime", "lat", "lon")
    grid.name = variable_name
    grid.attrs = dict(attrs)
    grid.attrs["model_var"] = f"quantile_regression_random_forest:{variable_name}"
    return ensure_grid(grid)


def predictions_to_station(
    template: pd.DataFrame,
    values: np.ndarray,
    quantiles: list[float],
    variable_name: str,
    attrs: dict,
) -> pd.DataFrame:
    pieces = []
    for index, quantile in enumerate(quantiles):
        part = template[["level", "time", "dtime", "id", "lon", "lat"]].copy()
        part["member"] = float(quantile)
        part[variable_name] = np.asarray(values[:, index], dtype=np.float32)
        pieces.append(part)
    station = pd.concat(pieces, ignore_index=True)
    station.attrs = dict(attrs)
    station.attrs["dtime_units"] = lead_units(attrs.get("dtime_units", "hour"))
    station.attrs["model_var"] = f"quantile_regression_random_forest:{variable_name}"
    return ensure_station(station)


def _quantile_label(quantile: float) -> str:
    return f"{float(quantile):.6g}"
