"""Merged grid EMOS modules (constants, domain, convert, validate, pipeline)."""

from __future__ import annotations

from typing import Any, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import xarray as xr

from emos_core import ApplyEMOS, EstimateCoefficientsForEnsembleCalibration
from emos_xr_utils import (
    REALIZATION_DIM,
    SPOT_DIM,
    TIME_DIM,
    as_dataarray,
    as_dataset,
    enforce_coordinate_ordering,
    get_forecast_type,
    is_gridded_data,
    pd_timestamp_to_datetime,
    stack_lat_lon_to_spot as _stack_lat_lon_to_spot,
    unstack_spot_to_lat_lon as _unstack_spot_to_lat_lon,
)

# --- grid_constants ---
GRID_MEMBER_DIM = "member"
GRID_LEVEL_DIM = "level"
GRID_TIME_DIM = "time"
GRID_DTIME_DIM = "dtime"
GRID_LAT_DIM = "lat"
GRID_LON_DIM = "lon"

GRID_SPATIAL_DIMS = (GRID_LEVEL_DIM, GRID_LAT_DIM, GRID_LON_DIM)
GRID_FORECAST_DIMS = (
    GRID_MEMBER_DIM,
    GRID_LEVEL_DIM,
    GRID_TIME_DIM,
    GRID_DTIME_DIM,
    GRID_LAT_DIM,
    GRID_LON_DIM,
)
GRID_TRUTH_DIMS = GRID_FORECAST_DIMS

# 静态预测因子在这些轴上必须为单例（长度为 1）。
GRID_ADDITIONAL_SINGLETON_DIMS = (
    GRID_MEMBER_DIM,
    GRID_TIME_DIM,
    GRID_DTIME_DIM,
)

SPATIAL_COORD_PRECISION = 6

GridInput = Union[xr.DataArray, xr.Dataset, pd.DataFrame]
InputField = Union[xr.DataArray, xr.Dataset]
AdditionalFields = Optional[Sequence[GridInput]]


def dataframe_to_grid_dataarray(
    df: pd.DataFrame,
    value_col: str | None = None,
    dim_cols: Sequence[str] | None = None,
) -> xr.DataArray:
    """
    六列长表 → 六维 DataArray。

    相同 (lat, lon) 视为同一站点/格点位置。
    """
    dim_cols = tuple(dim_cols or GRID_FORECAST_DIMS)
    missing = [d for d in dim_cols if d not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing dimension columns: {missing}")
    if value_col is None:
        value_cols = [c for c in df.columns if c not in dim_cols]
        if len(value_cols) != 1:
            raise ValueError(
                f"Cannot infer value column; provide value_col. "
                f"Non-dimension columns: {value_cols}"
            )
        value_col = value_cols[0]
    if df.duplicated(subset=list(dim_cols)).any():
        raise ValueError(
            f"Duplicate rows for dimension columns {dim_cols}; "
            "each (member, level, time, dtime, lat, lon) must be unique"
        )
    work = df.copy()
    for col in (GRID_LAT_DIM, GRID_LON_DIM):
        if col in work.columns:
            work[col] = np.round(
                work[col].astype(np.float64),
                SPATIAL_COORD_PRECISION,
            )
    da = (
        work.set_index(list(dim_cols))[value_col]
        .to_xarray()
        .transpose(*dim_cols)
    )
    da.name = value_col
    da.attrs.setdefault("units", "1")
    return da


def ensure_level_dimension(
    da: xr.DataArray,
    default_level: float | None = None,
) -> xr.DataArray:
    """确保存在 level 维（单层时长度为 1）。"""
    if GRID_LEVEL_DIM in da.dims:
        return da
    level_val = float(
        default_level if default_level is not None else da.attrs.get("default_level", 850.0)
    )
    return da.expand_dims({GRID_LEVEL_DIM: [level_val]})


def normalize_grid_input(
    obj: GridInput,
    var_name: str | None = None,
    value_col: str | None = None,
) -> xr.DataArray:
    """
    统一输入为六维 DataArray：member/level/time/dtime/lat/lon。

    支持 xarray 或六列 DataFrame。
    """
    if isinstance(obj, pd.DataFrame):
        return ensure_level_dimension(dataframe_to_grid_dataarray(obj, value_col=value_col))
    da = as_dataarray(obj, var_name=var_name)
    if REALIZATION_DIM in da.dims and GRID_MEMBER_DIM not in da.dims:
        da = da.rename({REALIZATION_DIM: GRID_MEMBER_DIM})
    da = ensure_level_dimension(da)
    try:
        da = ensure_dtime_dimension(da)
    except ValueError:
        pass
    return round_spatial_coords(da)


def normalize_grid_inputs(
    historic_forecasts: GridInput,
    truths: GridInput,
    additional_fields: AdditionalFields = None,
    var_name: str | None = None,
    value_col: str | None = None,
) -> tuple[xr.DataArray, xr.DataArray, List[xr.DataArray] | None]:
    """批量规范化训练/订正输入。"""
    fo = normalize_grid_input(historic_forecasts, var_name=var_name, value_col=value_col)
    ob = normalize_grid_input(truths, var_name=var_name, value_col=value_col)
    add: List[xr.DataArray] | None = None
    if additional_fields:
        add = [
            normalize_grid_input(f, var_name=var_name, value_col=value_col)
            for f in additional_fields
        ]
    return fo, ob, add


def levels_to_process(da: xr.DataArray, levels: Sequence[float] | None) -> List[float]:
    if levels is not None:
        return [float(v) for v in levels]
    return [float(v) for v in da[GRID_LEVEL_DIM].values]


# --- domain ---

DomainType = Literal["grid"]


def _has_grid_dtime(da: xr.DataArray) -> bool:
    return (
        GRID_DTIME_DIM in da.dims
        or GRID_DTIME_DIM in da.coords
        or "reference_dtime" in da.attrs
    )


def is_user_grid_format(da: xr.DataArray) -> bool:
    """用户格点命名：member/level/time/lat/lon（以及 dtime 维或标量 dtime 坐标）。"""
    core = (
        GRID_MEMBER_DIM,
        GRID_LEVEL_DIM,
        GRID_TIME_DIM,
        GRID_LAT_DIM,
        GRID_LON_DIM,
    )
    if not all(dim in da.dims for dim in core):
        return False
    return _has_grid_dtime(da)


def is_user_grid_apply_format(da: xr.DataArray) -> bool:
    """用户格点订正输入：集合含 member；概率/分位值预报可无 member。"""
    core = (GRID_LEVEL_DIM, GRID_TIME_DIM, GRID_LAT_DIM, GRID_LON_DIM)
    if not all(dim in da.dims for dim in core) or not _has_grid_dtime(da):
        return False
    if GRID_MEMBER_DIM in da.dims:
        return True
    return "threshold" in da.dims or any("percentile" in d for d in da.dims)


def validate_grid_format(da: xr.DataArray, *, apply: bool = False) -> None:
    """校验输入是否为六维（或订正阶段允许的）格点/站点格式。"""
    ok = is_user_grid_apply_format(da) if apply else is_user_grid_format(da)
    if not ok:
        expected = (
            f"{GRID_FORECAST_DIMS} (training)"
            if not apply
            else f"{GRID_MEMBER_DIM!r} or prob/percentile with "
            f"{GRID_LEVEL_DIM!r}/{GRID_TIME_DIM!r}/{GRID_DTIME_DIM!r}/"
            f"{GRID_LAT_DIM!r}/{GRID_LON_DIM!r}"
        )
        raise ValueError(
            f"Expected unified grid/station input with dims {expected}; got {da.dims}"
        )


def check_coefficients_match_forecast(
    forecast: xr.DataArray,
    coefficients: xr.Dataset,
) -> None:
    """校验系数含预报所需的 level 与 lat/lon。"""
    if GRID_LEVEL_DIM not in coefficients.dims:
        raise ValueError(f"coefficients must include {GRID_LEVEL_DIM!r} dimension")
    if "level" in forecast.dims:
        requested = set(float(v) for v in forecast[GRID_LEVEL_DIM].values)
        available = set(float(v) for v in coefficients[GRID_LEVEL_DIM].values)
        missing = requested - available
        if missing:
            raise ValueError(
                f"coefficients missing level(s) present in forecast: {sorted(missing)}"
            )
# --- grid_convert ---


def ensure_dtime_dimension(da: xr.DataArray) -> xr.DataArray:
    """确保预报保留长度为 1 的 dtime 维度，以满足应用阶段输入要求。"""
    if GRID_DTIME_DIM in da.dims:
        if da.sizes[GRID_DTIME_DIM] != 1:
            raise ValueError(
                f"Apply expects a single {GRID_DTIME_DIM}; got {da.sizes[GRID_DTIME_DIM]}"
            )
        return da
    if GRID_DTIME_DIM in da.coords:
        dtime_val = np.atleast_1d(da[GRID_DTIME_DIM].values)[0]
        da = da.drop_vars(GRID_DTIME_DIM)
        return da.expand_dims({GRID_DTIME_DIM: [dtime_val]})
    if "reference_dtime" in da.attrs:
        dtime_val = da.attrs["reference_dtime"]
        units = da.attrs.get("dtime_units", "hour")
        return da.expand_dims({GRID_DTIME_DIM: [dtime_val]}).assign_attrs(
            {**da.attrs, "dtime_units": units}
        )
    raise ValueError(
        f"Apply input must retain {GRID_DTIME_DIM}, include it as a scalar "
        "coordinate, or provide reference_dtime in attributes"
    )


def select_level(da: xr.DataArray, level: float) -> xr.DataArray:
    """选取一个垂直层并丢弃 level 维度。"""
    if GRID_LEVEL_DIM not in da.dims:
        raise ValueError(f"Input has no {GRID_LEVEL_DIM} dimension")
    selected = da.sel({GRID_LEVEL_DIM: level}, drop=True)
    if GRID_LEVEL_DIM in selected.dims:
        selected = selected.isel({GRID_LEVEL_DIM: 0}, drop=True)
    return selected


def dtime_to_forecast_period(da: xr.DataArray) -> np.timedelta64:
    """
    将格点 dtime 坐标转换为 IMPROVER forecast_period（timedelta64[ns]）。

    变量 attrs 中的 dtime_units：'minute' 表示分钟，否则按小时处理。
    """
    if GRID_DTIME_DIM not in da.coords:
        raise ValueError(f"Missing {GRID_DTIME_DIM} coordinate")
    dtime_vals = da[GRID_DTIME_DIM].values
    if np.atleast_1d(dtime_vals).size != 1:
        raise ValueError(
            f"Expected a single {GRID_DTIME_DIM} value for conversion; "
            f"got {np.atleast_1d(dtime_vals)}"
        )
    raw = np.atleast_1d(dtime_vals)[0]
    units = str(da.attrs.get("dtime_units", "hour")).lower().strip()
    if np.issubdtype(np.array(raw).dtype, np.timedelta64):
        return np.timedelta64(raw, "ns")
    if units == "minute":
        return np.timedelta64(int(raw), "m").astype("timedelta64[ns]")
    return np.timedelta64(int(raw), "h").astype("timedelta64[ns]")


def forecast_period_to_dtime(forecast_period: np.timedelta64) -> Tuple[float, str]:
    """将内部 forecast_period 映射回格点 dtime 与 dtime_units。"""
    fp_ns = np.timedelta64(forecast_period, "ns")
    minutes = fp_ns / np.timedelta64(1, "m")
    if minutes % 60 == 0:
        return float(minutes / 60), "hour"
    return float(minutes), "minute"


def _validity_times(init_times: np.ndarray, forecast_period: np.timedelta64) -> np.ndarray:
    init = pd.to_datetime(init_times)
    delta = pd.to_timedelta(np.timedelta64(forecast_period, "ns"))
    return (init + delta).to_numpy(dtype="datetime64[ns]")


def _truth_time_lookup(truth: xr.DataArray) -> dict:
    lookup = {}
    for t in truth[GRID_TIME_DIM].values:
        lookup[pd.Timestamp(t)] = t
    return lookup


def _match_validity_to_truth(validity: np.datetime64, lookup: dict) -> Optional[np.datetime64]:
    key = pd.Timestamp(validity)
    if key in lookup:
        return lookup[key]
    for truth_key, truth_val in lookup.items():
        if truth_key.to_pydatetime() == pd.Timestamp(validity).to_pydatetime():
            return truth_val
    return None


def stack_lat_lon_to_spot(da: xr.DataArray) -> xr.DataArray:
    """将 lat/lon 维度堆叠为 spot_index。"""
    return _stack_lat_lon_to_spot(da, lat_dim=GRID_LAT_DIM, lon_dim=GRID_LON_DIM)


def unstack_spot_to_lat_lon(
    da: xr.DataArray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> xr.DataArray:
    """将 spot_index 还原为 lat/lon 维度。"""
    return _unstack_spot_to_lat_lon(
        da, lat, lon, lat_dim=GRID_LAT_DIM, lon_dim=GRID_LON_DIM
    )


def _rename_member_to_realization(da: xr.DataArray) -> xr.DataArray:
    if GRID_MEMBER_DIM not in da.dims:
        return da
    out = da.rename({GRID_MEMBER_DIM: REALIZATION_DIM})
    out = out.assign_coords(
        {REALIZATION_DIM: out[REALIZATION_DIM].values.astype(np.int32)}
    )
    out[REALIZATION_DIM].attrs.setdefault("units", "1")
    return out


def _rename_realization_to_member(da: xr.DataArray) -> xr.DataArray:
    if REALIZATION_DIM not in da.dims:
        return da
    out = da.rename({REALIZATION_DIM: GRID_MEMBER_DIM})
    return out.assign_coords(
        {GRID_MEMBER_DIM: out[GRID_MEMBER_DIM].values.astype(np.int32)}
    )



def _attach_improver_time_coords(
    da: xr.DataArray,
    validity_times: np.ndarray,
    init_times: np.ndarray,
    forecast_period: np.timedelta64,
) -> xr.DataArray:
    da = da.assign_coords({TIME_DIM: validity_times})
    da = da.assign_coords(
        {
            "forecast_reference_time": (TIME_DIM, init_times),
            "forecast_period": forecast_period,
        }
    )
    da["forecast_reference_time"].attrs.setdefault("units", "seconds since 1970-01-01 00:00:00")
    da["forecast_period"].attrs.setdefault("units", "seconds")
    return da


def compact_spatial_for_internal(da: xr.DataArray) -> xr.DataArray:
    """
    将 lat/lon 堆叠为 spot_index，并仅保留有数据的站点。

    稀疏伪格点（站点）训练/订正时跳过全 NaN 的 (lat, lon) 组合。
    """
    if SPOT_DIM in da.dims:
        return da
    if GRID_LAT_DIM not in da.dims or GRID_LON_DIM not in da.dims:
        return da
    stacked = stack_lat_lon_to_spot(da)
    for name, coord in da.coords.items():
        if name in (GRID_LAT_DIM, GRID_LON_DIM, SPOT_DIM):
            continue
        if name in stacked.dims or name in stacked.coords:
            continue
        stacked = stacked.assign_coords({name: coord})
    other_axes = [d for d in stacked.dims if d != SPOT_DIM]
    if other_axes:
        keep = stacked.notnull().any(dim=other_axes)
    else:
        keep = stacked.notnull()
    if not bool(keep.any()):
        return stacked
    if bool(keep.all()):
        return stacked
    valid_ids = stacked[SPOT_DIM].values[keep.values]
    return stacked.sel({SPOT_DIM: valid_ids})


def _should_compact_spatial(
    forecast: xr.DataArray,
    truth: xr.DataArray,
) -> bool:
    n_grid = forecast.sizes[GRID_LAT_DIM] * forecast.sizes[GRID_LON_DIM]
    valid_lats, _ = compute_valid_station_pairs(forecast, truth)
    return len(valid_lats) < n_grid


def to_internal_training(
    forecast: xr.DataArray,
    truth: xr.DataArray,
    additional_fields: Optional[List[xr.DataArray]] = None,
) -> Tuple[xr.DataArray, xr.DataArray, List[xr.DataArray]]:
    """
    格点训练输入 -> IMPROVER 语义。

    内部 ``time`` 为有效时间；``forecast_reference_time`` 存储起报时间。
    """
    forecast_period = dtime_to_forecast_period(forecast)
    lookup = _truth_time_lookup(truth)
    hf_slices = []
    tr_slices = []
    init_matched = []
    validity_matched = []

    for init_time in forecast[GRID_TIME_DIM].values:
        validity = _validity_times(np.array([init_time]), forecast_period)[0]
        truth_time = _match_validity_to_truth(validity, lookup)
        if truth_time is None:
            continue
        fo_slice = forecast.sel({GRID_TIME_DIM: init_time}).isel(
            {GRID_DTIME_DIM: 0}, drop=True
        )
        ob_slice = truth.sel({GRID_TIME_DIM: truth_time}).isel(
            {GRID_MEMBER_DIM: 0, GRID_DTIME_DIM: 0}, drop=True
        )
        hf_slices.append(fo_slice)
        tr_slices.append(ob_slice)
        init_matched.append(init_time)
        validity_matched.append(truth_time)

    if not hf_slices:
        raise ValueError(
            "No matching validity times found between forecast and truth "
            f"for forecast_period={forecast_period}"
        )

    fo_matched = xr.concat(hf_slices, dim=TIME_DIM)
    fo_matched = fo_matched.assign_coords(
        {TIME_DIM: np.array(validity_matched, dtype="datetime64[ns]")}
    )
    ob_matched = xr.concat(tr_slices, dim=TIME_DIM)
    ob_matched = ob_matched.assign_coords(
        {TIME_DIM: np.array(validity_matched, dtype="datetime64[ns]")}
    )

    fo_matched = _rename_member_to_realization(fo_matched)
    fo_matched = fo_matched.transpose(
        REALIZATION_DIM,
        TIME_DIM,
        GRID_LAT_DIM,
        GRID_LON_DIM,
    )
    fo_matched = enforce_coordinate_ordering(fo_matched, [REALIZATION_DIM, TIME_DIM])
    fo_matched = _attach_improver_time_coords(
        fo_matched,
        validity_times=np.array(validity_matched, dtype="datetime64[ns]"),
        init_times=np.array(init_matched, dtype="datetime64[ns]"),
        forecast_period=forecast_period,
    )

    ob_internal = ob_matched.transpose(TIME_DIM, GRID_LAT_DIM, GRID_LON_DIM)

    if _should_compact_spatial(forecast, truth):
        fo_matched = compact_spatial_for_internal(fo_matched)
        ob_internal = compact_spatial_for_internal(ob_internal)

    add_internal: List[xr.DataArray] = []
    if additional_fields:
        for field in additional_fields:
            squeezed = field.isel(
                {GRID_MEMBER_DIM: 0, GRID_TIME_DIM: 0, GRID_DTIME_DIM: 0},
                drop=True,
            )
            if GRID_LEVEL_DIM in squeezed.dims:
                squeezed = squeezed.squeeze(GRID_LEVEL_DIM, drop=True)
            slab = squeezed.transpose(GRID_LAT_DIM, GRID_LON_DIM)
            if SPOT_DIM not in fo_matched.dims:
                add_internal.append(slab)
            else:
                add_internal.append(compact_spatial_for_internal(slab))

    return fo_matched, ob_internal, add_internal


def _to_internal_static_fields(
    additional_fields: Optional[List[xr.DataArray]],
) -> List[xr.DataArray]:
    """将格点静态预测因子转为内部 lat/lon 形式。"""
    add_internal: List[xr.DataArray] = []
    if not additional_fields:
        return add_internal
    for field in additional_fields:
        squeezed = field.isel(
            {GRID_MEMBER_DIM: 0, GRID_TIME_DIM: 0, GRID_DTIME_DIM: 0},
            drop=True,
        )
        if GRID_LEVEL_DIM in squeezed.dims:
            squeezed = squeezed.squeeze(GRID_LEVEL_DIM, drop=True)
        add_internal.append(squeezed.transpose(GRID_LAT_DIM, GRID_LON_DIM))
    return add_internal


def to_internal_apply(
    forecast: xr.DataArray,
    additional_fields: Optional[List[xr.DataArray]] = None,
) -> Tuple[xr.DataArray, List[xr.DataArray], np.timedelta64]:
    """
    格点应用输入 -> IMPROVER 语义。

    内部 ``time`` 保留格点起报时间；``forecast_reference_time`` 与之对应。
    """
    forecast_period = dtime_to_forecast_period(forecast)
    if forecast.sizes[GRID_DTIME_DIM] != 1:
        raise ValueError(
            f"Apply expects a single {GRID_DTIME_DIM}; got {forecast.sizes[GRID_DTIME_DIM]}"
        )

    fc = forecast.isel({GRID_DTIME_DIM: 0}, drop=True)
    fc = _rename_member_to_realization(fc)
    fc = fc.rename({GRID_TIME_DIM: TIME_DIM})
    fc = fc.transpose(REALIZATION_DIM, TIME_DIM, GRID_LAT_DIM, GRID_LON_DIM)
    fc = enforce_coordinate_ordering(fc, [REALIZATION_DIM, TIME_DIM])
    init_times = fc[TIME_DIM].values
    fc = fc.assign_coords(
        {
            "forecast_reference_time": (TIME_DIM, init_times),
            "forecast_period": forecast_period,
        }
    )
    fc["forecast_reference_time"].attrs.setdefault("units", "seconds since 1970-01-01 00:00:00")
    fc["forecast_period"].attrs.setdefault("units", "seconds")

    if GRID_LAT_DIM in fc.dims and GRID_LON_DIM in fc.dims:
        fc = compact_spatial_for_internal(fc)

    add_internal = _to_internal_static_fields(additional_fields)
    if add_internal and SPOT_DIM in fc.dims:
        add_internal = [compact_spatial_for_internal(field) for field in add_internal]

    return fc, add_internal, forecast_period


def to_internal_prob_template(
    prob_template: xr.DataArray,
    forecast_period: np.timedelta64,
) -> xr.DataArray:
    """将格点概率模板转换为内部 threshold + spot_index 形式。"""
    if "threshold" not in prob_template.dims:
        raise ValueError("prob_template must contain a threshold dimension")
    tpl = prob_template.copy(deep=True)
    if GRID_MEMBER_DIM in tpl.dims:
        raise ValueError("prob_template must use threshold, not member")
    if GRID_DTIME_DIM in tpl.dims:
        if tpl.sizes[GRID_DTIME_DIM] != 1:
            raise ValueError(f"prob_template {GRID_DTIME_DIM} must have length 1")
        tpl = tpl.isel({GRID_DTIME_DIM: 0}, drop=True)
    if GRID_LEVEL_DIM in tpl.dims:
        if tpl.sizes[GRID_LEVEL_DIM] != 1:
            raise ValueError(f"prob_template {GRID_LEVEL_DIM} must have length 1 here")
        tpl = tpl.isel({GRID_LEVEL_DIM: 0}, drop=True)
    tpl = tpl.rename({GRID_TIME_DIM: TIME_DIM})
    if GRID_LAT_DIM in tpl.dims and GRID_LON_DIM in tpl.dims:
        tpl = tpl.transpose(
            "threshold",
            TIME_DIM,
            GRID_LAT_DIM,
            GRID_LON_DIM,
            missing_dims="ignore",
        )
        tpl = compact_spatial_for_internal(tpl)
    init_times = tpl[TIME_DIM].values
    tpl = tpl.assign_coords(
        {
            "forecast_reference_time": (TIME_DIM, init_times),
            "forecast_period": forecast_period,
        }
    )
    return tpl


def scatter_spot_coeff_to_lat_lon(
    coeff: xr.DataArray,
    lat: np.ndarray,
    lon: np.ndarray,
) -> xr.DataArray:
    """将部分 spot_index 系数散射回完整 lat/lon 网格（空位 NaN）。"""
    if SPOT_DIM not in coeff.dims:
        return coeff
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    n_lon = len(lon)
    other_dims = [d for d in coeff.dims if d != SPOT_DIM]
    out_shape = [coeff.sizes[d] for d in other_dims] + [len(lat), len(lon)]
    data = np.full(out_shape, np.nan, dtype=np.float32)
    spot_lats = coeff[GRID_LAT_DIM].values if GRID_LAT_DIM in coeff.coords else None
    spot_lons = coeff[GRID_LON_DIM].values if GRID_LON_DIM in coeff.coords else None
    spot_ids = coeff[SPOT_DIM].values
    for i, spot_id in enumerate(spot_ids):
        if spot_lats is not None and spot_lons is not None:
            la = float(spot_lats[i])
            lo = float(spot_lons[i])
            lat_match = np.where(np.isclose(lat, la))[0]
            lon_match = np.where(np.isclose(lon, lo))[0]
            if len(lat_match) == 0 or len(lon_match) == 0:
                continue
            li = int(lat_match[0])
            lj = int(lon_match[0])
        else:
            flat_id = int(spot_id)
            li = flat_id // n_lon
            lj = flat_id % n_lon
            if li >= len(lat) or lj >= len(lon):
                continue
        src = coeff.isel({SPOT_DIM: i}).values
        data[(Ellipsis, li, lj)] = src
    coords = {d: coeff.coords[d] for d in other_dims}
    for c in coeff.coords:
        if c not in coords and c not in (GRID_LAT_DIM, GRID_LON_DIM, SPOT_DIM):
            coords[c] = coeff.coords[c]
    coords[GRID_LAT_DIM] = lat
    coords[GRID_LON_DIM] = lon
    return xr.DataArray(
        data,
        dims=other_dims + [GRID_LAT_DIM, GRID_LON_DIM],
        coords=coords,
        attrs=coeff.attrs,
        name=coeff.name,
    )


def coefficients_to_grid(
    coefficients: xr.Dataset,
    level: float,
    lat: np.ndarray,
    lon: np.ndarray,
    point_by_point: bool,
) -> xr.Dataset:
    """将 EMOS 系数 Dataset 映射回格点 level/lat/lon 坐标。"""
    out_vars = {}
    for name, da in coefficients.data_vars.items():
        coeff = da.copy(deep=True)
        if point_by_point and SPOT_DIM in coeff.dims:
            if coeff.sizes[SPOT_DIM] == len(lat) * len(lon):
                coeff = unstack_spot_to_lat_lon(coeff, lat, lon)
            else:
                coeff = scatter_spot_coeff_to_lat_lon(coeff, lat, lon)
        elif point_by_point and GRID_LAT_DIM not in coeff.dims:
            raise ValueError("point_by_point coefficients require lat/lon or spot_index")
        coeff = coeff.expand_dims({GRID_LEVEL_DIM: [level]})
        out_vars[name] = coeff
    ds = xr.Dataset(out_vars)
    ds.attrs.update(coefficients.attrs)
    ds.attrs["emos_domain"] = "grid"
    if "forecast_period" in coefficients.coords:
        dtime_val, dtime_units = forecast_period_to_dtime(
            coefficients.coords["forecast_period"].values
        )
        ds.attrs["dtime_units"] = dtime_units
        ds.attrs["reference_dtime"] = dtime_val
    return ds


def merge_level_coefficients(level_datasets: List[xr.Dataset]) -> xr.Dataset:
    """沿 level 维合并各层系数 Dataset。"""
    if not level_datasets:
        raise ValueError("No coefficient datasets to merge")
    if len(level_datasets) == 1:
        return level_datasets[0]
    return xr.concat(level_datasets, dim=GRID_LEVEL_DIM)


def align_coefficients_to_forecast(
    coefficients: xr.Dataset,
    forecast_internal: xr.DataArray,
) -> xr.Dataset:
    """订正时将系数空间维与已压缩的预报 spot_index 对齐。"""
    if SPOT_DIM not in forecast_internal.dims:
        return coefficients
    out_vars = {}
    for name, da in coefficients.data_vars.items():
        coeff = da
        if GRID_LEVEL_DIM in coeff.dims:
            coeff = coeff.squeeze(GRID_LEVEL_DIM, drop=True)
        if SPOT_DIM in coeff.dims:
            out_vars[name] = coeff.sel({SPOT_DIM: forecast_internal[SPOT_DIM].values})
        elif GRID_LAT_DIM in coeff.dims and GRID_LON_DIM in coeff.dims:
            stacked = stack_lat_lon_to_spot(coeff)
            out_vars[name] = stacked.sel({SPOT_DIM: forecast_internal[SPOT_DIM].values})
        else:
            out_vars[name] = coeff
    ds = xr.Dataset(out_vars)
    ds.attrs.update(coefficients.attrs)
    if "forecast_period" in coefficients.coords:
        ds = ds.assign_coords(forecast_period=coefficients.coords["forecast_period"])
    if "forecast_reference_time" in coefficients.coords:
        ds = ds.assign_coords(
            forecast_reference_time=coefficients.coords["forecast_reference_time"]
        )
    return ds


def coefficients_to_internal(
    coeff_level: xr.Dataset,
    template: xr.DataArray,
) -> xr.Dataset:
    """将格点系数传递至内部格式（已使用与 IMPROVER 相同的 lat/lon）。"""
    out_vars = {}
    for name, da in coeff_level.data_vars.items():
        coeff = da
        if GRID_LEVEL_DIM in coeff.dims:
            coeff = coeff.squeeze(GRID_LEVEL_DIM, drop=True)
        out_vars[name] = coeff
    ds = xr.Dataset(out_vars)
    ds.attrs.update(coeff_level.attrs)
    ds = ds.assign_coords(forecast_period=dtime_to_forecast_period(template))
    if "forecast_reference_time" not in ds.coords:
        init_times = template[GRID_TIME_DIM].values
        ds = ds.assign_coords(forecast_reference_time=init_times.max())
    return ds


def merge_level_forecasts(level_datasets: List[xr.Dataset]) -> xr.Dataset:
    """沿 level 维合并各层预报 Dataset。"""
    if not level_datasets:
        raise ValueError("No forecast datasets to merge")
    if len(level_datasets) == 1:
        return level_datasets[0]
    return xr.concat(level_datasets, dim=GRID_LEVEL_DIM)


def forecast_to_grid(
    result: Union[xr.DataArray, xr.Dataset],
    template: xr.DataArray,
    level: float,
    forecast_period: np.timedelta64,
    var_name: Optional[str] = None,
) -> xr.Dataset:
    """将 EMOS 应用输出转换回六维格点命名。"""
    da = as_dataarray(result, var_name=var_name)
    lat = template[GRID_LAT_DIM].values
    lon = template[GRID_LON_DIM].values
    if SPOT_DIM in da.dims and GRID_LAT_DIM not in da.coords:
        n_lon = len(lon)
        spot_ids = da[SPOT_DIM].values.astype(np.int64)
        da = da.assign_coords(
            {
                GRID_LAT_DIM: (SPOT_DIM, lat[spot_ids // n_lon]),
                GRID_LON_DIM: (SPOT_DIM, lon[spot_ids % n_lon]),
            }
        )
    if SPOT_DIM in da.dims:
        if da.sizes[SPOT_DIM] == len(lat) * len(lon):
            da = unstack_spot_to_lat_lon(da, lat, lon)
        else:
            da = scatter_spot_coeff_to_lat_lon(da, lat, lon)
    if REALIZATION_DIM in da.dims:
        da = _rename_realization_to_member(da)

    if TIME_DIM in da.dims:
        da = da.rename({TIME_DIM: GRID_TIME_DIM})

    dtime_val, dtime_units = forecast_period_to_dtime(forecast_period)
    da = da.expand_dims({GRID_DTIME_DIM: [dtime_val]})
    da = da.expand_dims({GRID_LEVEL_DIM: [level]})
    da.attrs["dtime_units"] = dtime_units

    template_dims = (
        GRID_MEMBER_DIM,
        GRID_LEVEL_DIM,
        GRID_TIME_DIM,
        GRID_DTIME_DIM,
        GRID_LAT_DIM,
        GRID_LON_DIM,
    )
    skip_member = "threshold" in da.dims or any(
        "percentile" in d for d in da.dims
    )
    for dim in template_dims:
        if dim == GRID_MEMBER_DIM and skip_member:
            continue
        if dim not in da.dims and dim in template.dims:
            da = da.expand_dims({dim: template[dim].values})

    if "threshold" in da.dims:
        ordered = ["threshold"] + [
            d for d in template_dims if d in da.dims and d != GRID_MEMBER_DIM
        ]
    elif any("percentile" in d for d in da.dims):
        perc = next(d for d in da.dims if "percentile" in d)
        ordered = [perc] + [
            d for d in template_dims if d in da.dims and d != GRID_MEMBER_DIM
        ]
    else:
        ordered = [d for d in template_dims if d in da.dims]
    extra = [d for d in da.dims if d not in ordered]
    da = da.transpose(*ordered, *extra)
    return as_dataset(da)


def create_prob_template_from_grid(
    forecast: xr.DataArray,
    thresholds: Sequence[float],
    thresholds_operator: str,
    diagnostic_name: Optional[str] = None,
) -> xr.DataArray:
    """构建含 threshold 维度的格点概率模板。"""
    if GRID_MEMBER_DIM not in forecast.dims:
        raise ValueError(f"forecast must contain {GRID_MEMBER_DIM}")
    other_dims = [d for d in forecast.dims if d != GRID_MEMBER_DIM]
    new_shape = [len(thresholds)] + [forecast.sizes[d] for d in other_dims]
    prob_data = np.zeros(new_shape, dtype=np.float32)
    if GRID_LAT_DIM in forecast.dims and GRID_LON_DIM in forecast.dims:
        reduce_dims = [d for d in forecast.dims if d not in (GRID_LAT_DIM, GRID_LON_DIM)]
        valid = forecast.notnull().any(dim=reduce_dims)
        for t_idx in range(len(thresholds)):
            prob_data[t_idx] = np.where(valid.values, 0.0, np.nan)
    new_coords = {c: forecast[c] for c in forecast.coords if c != GRID_MEMBER_DIM}
    threshold_attrs = {
        "units": forecast.attrs.get("units", "1"),
        "spp__relative_to_threshold": thresholds_operator,
    }
    new_coords["threshold"] = (
        "threshold",
        np.array(thresholds, dtype=np.float32),
        threshold_attrs,
    )
    new_dims = ["threshold"] + other_dims
    diag = diagnostic_name or forecast.name or forecast.attrs.get(
        "standard_name", forecast.attrs.get("long_name", "unknown")
    )
    new_attrs = forecast.attrs.copy()
    new_attrs.update(
        {
            "long_name": f"probability_of_{diag}_{thresholds_operator}_threshold",
            "units": "1",
        }
    )
    return xr.DataArray(
        prob_data,
        dims=new_dims,
        coords=new_coords,
        attrs=new_attrs,
        name="probability",
    )


def to_internal_percentile_forecast(forecast: xr.DataArray) -> xr.DataArray:
    """将格点百分位预报转换为内部应用格式。"""
    fp = forecast.copy(deep=True)
    if GRID_DTIME_DIM in fp.dims:
        if fp.sizes[GRID_DTIME_DIM] != 1:
            raise ValueError("Percentile apply expects a single dtime")
        fp = fp.isel({GRID_DTIME_DIM: 0}, drop=True)
    forecast_period = dtime_to_forecast_period(forecast)
    fp = fp.rename({GRID_TIME_DIM: TIME_DIM})
    other = [d for d in fp.dims if d not in (TIME_DIM, GRID_LAT_DIM, GRID_LON_DIM)]
    fp = fp.transpose(*other, TIME_DIM, GRID_LAT_DIM, GRID_LON_DIM)
    init_times = fp[TIME_DIM].values
    if fp.sizes[TIME_DIM] == 1:
        fp = fp.assign_coords(
            forecast_reference_time=np.atleast_1d(init_times)[0],
            forecast_period=forecast_period,
        )
    else:
        fp = fp.assign_coords(
            {
                "forecast_reference_time": (TIME_DIM, init_times),
                "forecast_period": forecast_period,
            }
        )
    fp["forecast_reference_time"].attrs.setdefault(
        "units", "seconds since 1970-01-01 00:00:00"
    )
    if GRID_LAT_DIM in fp.dims and GRID_LON_DIM in fp.dims:
        fp = compact_spatial_for_internal(fp)
    return fp
# --- grid_validate ---

import numpy as np
import xarray as xr


InputField = Union[xr.DataArray, xr.Dataset]


def _require_dims(da: xr.DataArray, expected: Sequence[str], label: str) -> None:
    """校验 DataArray 是否包含期望的维度。"""
    missing = [d for d in expected if d not in da.dims]
    if missing:
        raise ValueError(f"{label} is missing dimension(s): {missing}")


def round_spatial_coords(da: xr.DataArray) -> xr.DataArray:
    """统一 lat/lon 坐标精度，避免训练/订正浮点不一致。"""
    updates = {}
    for coord in (GRID_LAT_DIM, GRID_LON_DIM):
        if coord in da.coords:
            updates[coord] = np.round(
                np.asarray(da[coord].values, dtype=np.float64),
                SPATIAL_COORD_PRECISION,
            )
    if updates:
        da = da.assign_coords(updates)
    return da


def _coords_equal(first: xr.DataArray, second: xr.DataArray, coord: str) -> bool:
    """比较两个 DataArray 的指定坐标值是否相等。"""
    if coord not in first.coords or coord not in second.coords:
        return False
    return np.array_equal(first[coord].values, second[coord].values)


def spatial_template_from_coefficients(coefficients: xr.Dataset) -> xr.DataArray:
    """从系数 Dataset 提取 level/lat/lon 空间模板。"""
    sample = coefficients["emos_coefficient_alpha"]
    dims = [d for d in GRID_SPATIAL_DIMS if d in sample.dims]
    coords = {d: sample[d] for d in dims}
    shape = [sample.sizes[d] for d in dims]
    return xr.DataArray(
        np.zeros(shape, dtype=np.float32),
        dims=dims,
        coords=coords,
    )


def align_spatial_to_reference(
    da: xr.DataArray,
    reference: xr.DataArray,
) -> xr.DataArray:
    """将 DataArray 的 level/lat/lon 对齐到参考网格（站点/格点订正匹配）。"""
    da = round_spatial_coords(da)
    reference = round_spatial_coords(reference)
    reindex = {
        c: reference[c]
        for c in GRID_SPATIAL_DIMS
        if c in da.dims and c in reference.coords
    }
    if reindex:
        da = da.reindex(reindex)
    return da


def compute_valid_station_pairs(
    historic_forecast: xr.DataArray,
    truth: xr.DataArray,
) -> tuple[list[float], list[float]]:
    """
    返回训练期预报与实况均有数据的 (lat, lon) 站点列表。

    稀疏 lat/lon 伪格点（站点）上仅有效位置参与；用于订正阶段校验。
    """
    hf = historic_forecast
    ob = truth
    hf_axes = [d for d in hf.dims if d not in GRID_SPATIAL_DIMS]
    ob_axes = [d for d in ob.dims if d not in GRID_SPATIAL_DIMS]
    hf_ok = hf.notnull().any(dim=hf_axes) if hf_axes else hf.notnull()
    ob_ok = ob.notnull().any(dim=ob_axes) if ob_axes else ob.notnull()
    mask = hf_ok & ob_ok

    valid_lats: list[float] = []
    valid_lons: list[float] = []
    for i, lat in enumerate(hf[GRID_LAT_DIM].values):
        for j, lon in enumerate(hf[GRID_LON_DIM].values):
            if bool(mask.isel({GRID_LAT_DIM: i, GRID_LON_DIM: j}).values):
                valid_lats.append(float(lat))
                valid_lons.append(float(lon))
    return valid_lats, valid_lons


def attach_training_station_metadata(
    coefficients: xr.Dataset,
    historic_forecast: xr.DataArray,
    truth: xr.DataArray,
) -> xr.Dataset:
    """在系数中记录训练有效站点，供订正阶段空间匹配。"""
    valid_lats, valid_lons = compute_valid_station_pairs(historic_forecast, truth)
    if not valid_lats:
        raise ValueError(
            "No valid (lat, lon) locations with both historic forecast and truth data"
        )
    coefficients.attrs["emos_valid_lat"] = valid_lats
    coefficients.attrs["emos_valid_lon"] = valid_lons
    coefficients.attrs["emos_n_stations"] = len(valid_lats)
    if GRID_DTIME_DIM in historic_forecast.coords:
        coefficients.attrs["emos_training_dtime"] = float(
            np.atleast_1d(historic_forecast[GRID_DTIME_DIM].values)[0]
        )
    return coefficients


def validate_apply_trained_stations(
    forecast: xr.DataArray,
    coefficients: xr.Dataset,
) -> None:
    """订正预报须覆盖训练期有效站点位置。"""
    valid_lats = coefficients.attrs.get("emos_valid_lat")
    valid_lons = coefficients.attrs.get("emos_valid_lon")
    if not valid_lats or not valid_lons:
        return

    missing: list[tuple[float, float]] = []
    for lat, lon in zip(valid_lats, valid_lons):
        point = forecast.sel({GRID_LAT_DIM: lat, GRID_LON_DIM: lon})
        if not np.isfinite(point.values).any():
            missing.append((lat, lon))
    if missing:
        shown = ", ".join(f"({la}, {lo})" for la, lo in missing[:5])
        extra = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        raise ValueError(
            "Apply forecast has no finite data at trained station location(s): "
            f"{shown}{extra}. Ensure lat/lon and time/dtime match training inputs."
        )


def validate_spatial_coords(
    *arrays: xr.DataArray,
    labels: Optional[Sequence[str]] = None,
) -> None:
    """确保所有输入的 level、lat、lon 坐标一致。"""
    if not arrays:
        return
    labels = labels or [f"input_{i}" for i in range(len(arrays))]
    reference = arrays[0]
    for coord in GRID_SPATIAL_DIMS:
        if coord not in reference.coords:
            raise ValueError(f"{labels[0]} is missing coordinate {coord!r}")
    for da, label in zip(arrays[1:], labels[1:], strict=False):
        for coord in GRID_SPATIAL_DIMS:
            if not _coords_equal(reference, da, coord):
                raise ValueError(
                    f"Spatial coordinate {coord!r} differs between "
                    f"{labels[0]!r} and {label!r}"
                )


def validate_truth_structure(truth: xr.DataArray) -> None:
    """实况须为六维，member 为 1 且 dtime 等于 0。"""
    _require_dims(truth, GRID_TRUTH_DIMS, "truth")
    if truth.sizes[GRID_MEMBER_DIM] != 1:
        raise ValueError(
            f"truth must have exactly one {GRID_MEMBER_DIM}; "
            f"got {truth.sizes[GRID_MEMBER_DIM]}"
        )
    if truth.sizes[GRID_DTIME_DIM] != 1:
        raise ValueError(
            f"truth must have {GRID_DTIME_DIM} length 1; "
            f"got {truth.sizes[GRID_DTIME_DIM]}"
        )
    dtime_val = np.atleast_1d(truth[GRID_DTIME_DIM].values)[0]
    if not np.isclose(dtime_val, 0):
        raise ValueError(f"truth {GRID_DTIME_DIM} must be 0; got {dtime_val}")


def validate_forecast_structure(forecast: xr.DataArray) -> None:
    """校验预报是否具有完整的格点预报维度。"""
    _require_dims(forecast, GRID_FORECAST_DIMS, "forecast")


def validate_apply_forecast_structure(forecast: xr.DataArray) -> None:
    """校验格点订正阶段预报维度（集合/概率/分位值输入）。"""
    ftype = get_forecast_type(forecast)
    if ftype == "realizations":
        validate_forecast_structure(forecast)
        return
    core = (
        GRID_LEVEL_DIM,
        GRID_TIME_DIM,
        GRID_DTIME_DIM,
        GRID_LAT_DIM,
        GRID_LON_DIM,
    )
    _require_dims(forecast, core, "forecast")
    if ftype == "percentiles" and not any("percentile" in d for d in forecast.dims):
        raise ValueError("percentile forecast is missing a percentile dimension")
    if ftype == "probabilities" and "threshold" not in forecast.dims:
        raise ValueError("probability forecast is missing threshold dimension")


def validate_additional_field(
    field: xr.DataArray,
    reference: xr.DataArray,
    label: str = "additional_field",
) -> None:
    """校验附加静态预测因子的结构与空间坐标。"""
    _require_dims(field, GRID_FORECAST_DIMS, label)
    validate_spatial_coords(reference, field, labels=("reference", label))
    for dim in GRID_ADDITIONAL_SINGLETON_DIMS:
        if field.sizes[dim] != 1:
            raise ValueError(
                f"{label} must have {dim} length 1; got {field.sizes[dim]}"
            )


def _init_hours(times: np.ndarray) -> set:
    """提取起报时间的小时集合。"""
    return {pd_timestamp_to_datetime(t).hour for t in np.atleast_1d(times)}


def validate_training_consistency(
    forecast: xr.DataArray,
    strict: bool = False,
) -> None:
    """可选校验：固定预报时效与一致的起报小时。"""
    dtime_vals = np.atleast_1d(forecast[GRID_DTIME_DIM].values)
    if len(dtime_vals) != 1 and not np.all(dtime_vals == dtime_vals[0]):
        msg = (
            f"Training expects a fixed {GRID_DTIME_DIM}; "
            f"got values {dtime_vals}"
        )
        if strict:
            raise ValueError(msg)
    init_hours = _init_hours(forecast[GRID_TIME_DIM].values)
    if len(init_hours) != 1:
        msg = (
            f"Training expects a single init-time hour; got hours {init_hours}"
        )
        if strict:
            raise ValueError(msg)


def validate_grid_inputs(
    historic_forecast: InputField,
    truth: InputField,
    additional_fields: Optional[Sequence[InputField]] = None,
    var_name: Optional[str] = None,
    strict_training: bool = False,
) -> tuple[xr.DataArray, xr.DataArray, List[xr.DataArray]]:
    """
    校验格点预报、实况及可选静态预测因子。

    返回可用于逐层处理的 DataArray。
    """
    fo = round_spatial_coords(as_dataarray(historic_forecast, var_name=var_name))
    ob = round_spatial_coords(as_dataarray(truth, var_name=var_name))
    ob = align_spatial_to_reference(ob, fo)
    validate_forecast_structure(fo)
    validate_truth_structure(ob)
    validate_spatial_coords(fo, ob, labels=("forecast", "truth"))

    add_fields: List[xr.DataArray] = []
    if additional_fields:
        for i, raw in enumerate(additional_fields):
            af = align_spatial_to_reference(as_dataarray(raw), fo)
            validate_additional_field(af, fo, label=f"additional_fields[{i}]")
            add_fields.append(af)

    valid_lats, valid_lons = compute_valid_station_pairs(fo, ob)
    if not valid_lats:
        raise ValueError(
            "No overlapping valid (lat, lon) between historic_forecast and truth"
        )

    validate_training_consistency(fo, strict=strict_training)
    return fo, ob, add_fields


def validate_apply_inputs(
    forecast: InputField,
    coefficients: xr.Dataset,
    additional_fields: Optional[Sequence[InputField]] = None,
    prob_template: Optional[InputField] = None,
    var_name: Optional[str] = None,
) -> tuple[xr.DataArray, xr.Dataset, List[xr.DataArray], Optional[xr.DataArray]]:
    """校验格点应用阶段的输入及系数空间域/域类型一致性。"""
    fc = ensure_dtime_dimension(as_dataarray(forecast, var_name=var_name))
    fc = round_spatial_coords(fc)
    validate_apply_forecast_structure(fc)
    if fc.sizes[GRID_DTIME_DIM] != 1:
        raise ValueError(
            f"Apply forecast must have a single {GRID_DTIME_DIM}; "
            f"got {fc.sizes[GRID_DTIME_DIM]}"
        )

    if GRID_LEVEL_DIM not in coefficients.dims:
        raise ValueError(f"coefficients must include {GRID_LEVEL_DIM} dimension")

    spatial_ref = spatial_template_from_coefficients(coefficients)
    fc = align_spatial_to_reference(fc, spatial_ref)
    validate_apply_trained_stations(fc, coefficients)

    training_dtime = coefficients.attrs.get("emos_training_dtime")
    if training_dtime is not None:
        fc_dtime = float(np.atleast_1d(fc[GRID_DTIME_DIM].values)[0])
        if not np.isclose(fc_dtime, float(training_dtime)):
            raise ValueError(
                f"Apply forecast dtime={fc_dtime} does not match training dtime="
                f"{training_dtime}"
            )

    add_fields: List[xr.DataArray] = []
    if additional_fields:
        for i, raw in enumerate(additional_fields):
            af = align_spatial_to_reference(as_dataarray(raw), spatial_ref)
            validate_additional_field(af, fc, label=f"additional_fields[{i}]")
            add_fields.append(af)

    coeff_ref = next(iter(coefficients.data_vars.values()))
    if GRID_LAT_DIM in coeff_ref.dims:
        validate_spatial_coords(fc, coeff_ref, labels=("forecast", "coefficients"))
    requested_levels = set(float(v) for v in fc[GRID_LEVEL_DIM].values)
    coeff_levels = set(float(v) for v in coefficients[GRID_LEVEL_DIM].values)
    missing = requested_levels - coeff_levels
    if missing:
        raise ValueError(
            f"coefficients missing level(s) present in forecast: {sorted(missing)}"
        )

    prob_da: Optional[xr.DataArray] = None
    if prob_template is not None:
        prob_da = align_spatial_to_reference(as_dataarray(prob_template, var_name=var_name), spatial_ref)
        if "threshold" not in prob_da.dims:
            raise ValueError("prob_template must contain a threshold dimension")
        validate_spatial_coords(fc, prob_da, labels=("forecast", "prob_template"))

    return fc, coefficients, add_fields, prob_da


def train_level_emos(
    fo: xr.DataArray,
    ob: xr.DataArray,
    add: List[xr.DataArray],
    level: float,
    trainer: EstimateCoefficientsForEnsembleCalibration,
    lat: np.ndarray,
    lon: np.ndarray,
    point_by_point: bool,
) -> xr.Dataset:
    """在单个 level 上训练 EMOS 系数。"""
    fo_level = select_level(fo, level)
    ob_level = select_level(ob, level)
    add_level = [select_level(af, level) for af in add] if add else None
    hf, tr, add_internal = to_internal_training(fo_level, ob_level, add_level)
    coeffs = trainer.process(
        historic_forecasts=hf,
        truths=tr,
        additional_fields=add_internal or None,
    )
    return coefficients_to_grid(coeffs, level, lat, lon, point_by_point)


def apply_level_emos(
    fc: xr.DataArray,
    coeffs: xr.Dataset,
    add: List[xr.DataArray],
    level: float,
    applier: ApplyEMOS,
    *,
    prob: xr.DataArray | None = None,
    var_name: str | None = None,
    realizations_count: int | None = None,
    ignore_ecc_bounds: bool = True,
    tolerate_time_mismatch: bool = False,
    predictor: str = "mean",
    randomise: bool = False,
    random_seed: int | None = None,
    return_parameters: bool = False,
) -> xr.Dataset:
    """在单个 level 上应用 EMOS 订正。"""
    fc_level = select_level(fc, level)
    add_level = [select_level(af, level) for af in add] if add else None
    coeff_level = coeffs.sel({GRID_LEVEL_DIM: level})
    coeff_base = coefficients_to_internal(coeff_level, fc_level)

    if prob is not None:
        prob_level = select_level(prob, level)
        fc_internal, add_internal, fp = to_internal_apply(fc_level, add_level)
        coeff_internal = align_coefficients_to_forecast(coeff_base, fc_internal)
        prob_internal = to_internal_prob_template(prob_level, fp)
        if SPOT_DIM in fc_internal.dims and "threshold" in prob_internal.dims:
            prob_internal = compact_spatial_for_internal(prob_internal)
        result = applier.process(
            forecast=fc_internal,
            coefficients=coeff_internal,
            additional_fields=add_internal or None,
            prob_template=prob_internal,
            tolerate_time_mismatch=tolerate_time_mismatch,
            predictor=predictor,
        )
        return forecast_to_grid(result, fc_level, level, fp, var_name=var_name)

    ftype = get_forecast_type(fc_level)
    if ftype == "percentiles":
        fc_internal = to_internal_percentile_forecast(fc_level)
        fp = fc_internal["forecast_period"].values
        coeff_internal = align_coefficients_to_forecast(coeff_base, fc_internal)
        add_internal = _to_internal_static_fields(add_level)
        if SPOT_DIM in fc_internal.dims and add_internal:
            add_internal = [compact_spatial_for_internal(f) for f in add_internal]
        result = applier.process(
            forecast=fc_internal,
            coefficients=coeff_internal,
            additional_fields=add_internal or None,
            realizations_count=realizations_count,
            ignore_ecc_bounds=ignore_ecc_bounds,
            tolerate_time_mismatch=tolerate_time_mismatch,
            predictor=predictor,
            randomise=randomise,
            random_seed=random_seed,
        )
    else:
        fc_internal, add_internal, fp = to_internal_apply(fc_level, add_level)
        coeff_internal = align_coefficients_to_forecast(coeff_base, fc_internal)
        result = applier.process(
            forecast=fc_internal,
            coefficients=coeff_internal,
            additional_fields=add_internal or None,
            realizations_count=realizations_count,
            ignore_ecc_bounds=ignore_ecc_bounds,
            tolerate_time_mismatch=tolerate_time_mismatch,
            predictor=predictor,
            randomise=randomise,
            random_seed=random_seed,
            return_parameters=return_parameters,
        )
        if return_parameters:
            return result

    return forecast_to_grid(result, fc_level, level, fp, var_name=var_name)


__all__ = [
    "AdditionalFields",
    "GridInput",
    "GRID_DTIME_DIM",
    "GRID_FORECAST_DIMS",
    "GRID_LAT_DIM",
    "GRID_LEVEL_DIM",
    "GRID_LON_DIM",
    "GRID_MEMBER_DIM",
    "GRID_TIME_DIM",
    "align_spatial_to_reference",
    "apply_level_emos",
    "attach_training_station_metadata",
    "check_coefficients_match_forecast",
    "compute_valid_station_pairs",
    "create_prob_template_from_grid",
    "dataframe_to_grid_dataarray",
    "ensure_dtime_dimension",
    "ensure_level_dimension",
    "levels_to_process",
    "merge_level_coefficients",
    "merge_level_forecasts",
    "normalize_grid_input",
    "round_spatial_coords",
    "spatial_template_from_coefficients",
    "train_level_emos",
    "validate_apply_inputs",
    "validate_apply_trained_stations",
    "validate_grid_format",
    "validate_grid_inputs",
]
