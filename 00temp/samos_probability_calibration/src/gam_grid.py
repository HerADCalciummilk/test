"""GAM helpers for six-dimensional xarray / DataFrame inputs, including static predictors."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from emos_grid import (
    GRID_DTIME_DIM,
    GRID_LAT_DIM,
    GRID_LEVEL_DIM,
    GRID_LON_DIM,
    GRID_MEMBER_DIM,
    GRID_TIME_DIM,
    GridInput,
    SPATIAL_COORD_PRECISION,
    normalize_grid_input,
)
from gam_models import GAMPredict

STATIC_MERGE_COLS = (GRID_LAT_DIM, GRID_LON_DIM)


def normalize_gam_input(obj: GridInput, var_name: str | None = None) -> xr.DataArray:
    """GAM 输入统一为六维 DataArray。"""
    return normalize_grid_input(obj, var_name=var_name)


def normalize_gam_fields(
    fields: Optional[Sequence[GridInput]],
    var_name: str | None = None,
) -> List[xr.DataArray] | None:
    """规范化静态/附加场列表。"""
    if not fields:
        return None
    return [normalize_gam_input(f, var_name=var_name) for f in fields]


def _squeeze_static_field(field: xr.DataArray) -> xr.DataArray:
    """静态因子在 member/time/dtime 上取单例，保留 lat/lon（及可选 level）。"""
    squeeze_dims = [
        d for d in (GRID_MEMBER_DIM, GRID_TIME_DIM, GRID_DTIME_DIM) if d in field.dims
    ]
    static = (
        field.isel({d: 0 for d in squeeze_dims}, drop=True) if squeeze_dims else field
    )
    if GRID_LEVEL_DIM in static.dims and static.sizes[GRID_LEVEL_DIM] == 1:
        static = static.squeeze(GRID_LEVEL_DIM, drop=True)
    if static.name is None:
        static = static.rename("static")
    return static


def add_static_feature_to_df(
    diagnostic_df: pd.DataFrame,
    static_field: xr.DataArray,
    *,
    feature_name: str | None = None,
    merge_cols: Sequence[str] = STATIC_MERGE_COLS,
    float_decimals: int = SPATIAL_COORD_PRECISION,
) -> pd.DataFrame:
    """
    将单个静态因子场并入诊断量长表（按 lat/lon 左连接）。

    与 IMPROVER ``add_static_feature_from_cube_to_df`` 语义一致：只保留诊断量上的站点，
    浮点坐标先按小数位缩放再合并，避免精度导致匹配失败。
    """
    static = _squeeze_static_field(static_field)
    feat_name = feature_name or static.name or "static"
    static_df = static.to_dataframe(name=feat_name).reset_index()

    keys = [
        c for c in merge_cols if c in diagnostic_df.columns and c in static_df.columns
    ]
    if not keys:
        raise ValueError(
            f"Cannot merge static field {feat_name!r}: need common columns among "
            f"{list(merge_cols)}; diagnostic has {list(diagnostic_df.columns)}, "
            f"static has {list(static_df.columns)}."
        )

    multiplier = float(10**float_decimals)
    left = diagnostic_df.copy()
    right = static_df[list(keys) + [feat_name]].copy()

    key_names: list[str] = []
    for col in keys:
        k = f"__merge_{col}"
        key_names.append(k)
        if pd.api.types.is_float_dtype(left[col]) or pd.api.types.is_float_dtype(
            right[col]
        ):
            left[k] = np.round(left[col].astype(np.float64) * multiplier).astype(
                np.int64
            )
            right[k] = np.round(right[col].astype(np.float64) * multiplier).astype(
                np.int64
            )
        else:
            left[k] = left[col]
            right[k] = right[col]

    if feat_name in left.columns:
        left = left.drop(columns=[feat_name])

    joined = left.merge(right[key_names + [feat_name]], on=key_names, how="left")
    return joined.drop(columns=key_names)


def prepare_data_for_gam(
    da: xr.DataArray,
    additional_fields: Optional[Sequence[xr.DataArray]] = None,
    *,
    float_decimals: int = SPATIAL_COORD_PRECISION,
) -> pd.DataFrame:
    """
    六维 DataArray → GAM 训练/预测长表，并按 (lat, lon) 融入静态因子。

    每个 ``additional_fields`` 中的场在 member/time/dtime 上取单例后，以场名为列并入。
    ``features`` 可同时包含坐标名（如 lat/lon）与静态列名（如 altitude/slope）。
    """
    value_name = da.name or "value"
    df = da.to_dataframe(name=value_name).reset_index()
    if not additional_fields:
        return df

    for field in additional_fields:
        df = add_static_feature_to_df(df, field, float_decimals=float_decimals)
    return df


def validate_gam_features(df: pd.DataFrame, features: Sequence[str]) -> None:
    """检查 features 是否都在长表中（坐标或已并入的静态列）。"""
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise ValueError(
            f"GAM features missing from dataframe: {missing}. "
            f"Available columns: {list(df.columns)}. "
            "Static predictors must be passed via additional_fields and "
            "listed in features by their variable names."
        )


def predictions_to_dataarray(
    template: xr.DataArray,
    df: pd.DataFrame,
    predictions: np.ndarray,
    value_name: str | None = None,
) -> xr.DataArray:
    """将 GAM 预测结果写回与 template 同形的 DataArray。"""
    value_name = value_name or template.name or "value"
    work = df.copy()
    work[value_name] = predictions.astype(np.float32)
    dim_cols = [d for d in template.dims if d in work.columns]
    out = work.set_index(dim_cols)[value_name].to_xarray().transpose(*template.dims)
    out.name = template.name
    out.attrs.update(template.attrs)
    return out


def calculate_grid_statistics(
    da: xr.DataArray,
    *,
    window_length: int = 11,
    valid_rolling_window_fraction: float = 0.5,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """
    计算训练统计量：有 member 维时沿 member 聚合；否则沿 time 滚动窗口。
    """
    if window_length < 3 or window_length % 2 == 0:
        raise ValueError(
            f"window_length must be an odd integer > 1; got {window_length}."
        )
    if not 0 <= valid_rolling_window_fraction <= 1:
        raise ValueError(
            "valid_rolling_window_fraction must be between 0 and 1; "
            f"got {valid_rolling_window_fraction}."
        )

    if GRID_MEMBER_DIM in da.dims and da.sizes[GRID_MEMBER_DIM] > 1:
        # ddof=1 matches Iris analysis.STD_DEV / IMPROVER collapse_realizations
        return da.mean(GRID_MEMBER_DIM), da.std(GRID_MEMBER_DIM, ddof=1)

    if GRID_TIME_DIM not in da.dims:
        raise ValueError(
            "Input must contain member or a multi-point time dimension for "
            f"statistics. dims={da.dims}"
        )
    if da.sizes[GRID_TIME_DIM] == 1:
        raise ValueError(
            "Single time point without member dimension cannot produce GAM statistics."
        )

    min_periods = max(1, int(np.ceil(window_length * valid_rolling_window_fraction)))
    rolled = da.rolling(
        {GRID_TIME_DIM: window_length},
        center=True,
        min_periods=min_periods,
    )
    return rolled.mean(), rolled.std(ddof=1)


def get_climatological_stats(
    da: xr.DataArray,
    gams: List,
    gam_features: Sequence[str],
    additional_fields: Optional[Sequence[xr.DataArray]] = None,
    *,
    sd_clip: float = 0.25,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """用已拟合 GAM 预测气候均值与标准差（features 含静态因子列）。"""
    if len(gams) != 2:
        raise ValueError("gams must contain exactly two fitted models (mean, sd).")
    df = prepare_data_for_gam(da, additional_fields)
    validate_gam_features(df, gam_features)

    feature_cols = list(gam_features)
    valid = df[feature_cols].notna().all(axis=1)
    mean_pred = np.full(len(df), np.nan, dtype=np.float64)
    sd_pred = np.full(len(df), np.nan, dtype=np.float64)
    if bool(valid.any()):
        predictor = GAMPredict()
        X = df.loc[valid, feature_cols].to_numpy(np.float64)
        mean_pred[valid.to_numpy()] = predictor.process(gams[0], X)
        sd_pred[valid.to_numpy()] = predictor.process(gams[1], X)
    sd_pred = np.clip(sd_pred, a_min=sd_clip, a_max=None)

    value_name = da.name or "value"
    mean_da = predictions_to_dataarray(da, df, mean_pred, value_name=value_name)
    sd_da = predictions_to_dataarray(da, df, sd_pred, value_name=value_name)
    return mean_da, sd_da


def calculate_climate_anomalies(
    diagnostic: xr.DataArray,
    mean: xr.DataArray,
    std: xr.DataArray | None = None,
) -> xr.DataArray:
    """(x - mean) / std；std 缺省时仅做距平。"""
    anom = diagnostic - mean
    standardized = std is not None
    if standardized:
        anom = anom / std
    out = anom.astype(np.float32)
    out.name = (
        f"{diagnostic.name}_standardized_anomaly"
        if standardized
        else f"{diagnostic.name}_anomaly"
    )
    out.attrs = diagnostic.attrs.copy()
    out.attrs["units"] = "1" if standardized else diagnostic.attrs.get("units", "1")
    return out


def transform_anomalies_to_original_units(
    location_parameter: xr.DataArray,
    scale_parameter: xr.DataArray,
    truth_mean: xr.DataArray,
    truth_sd: xr.DataArray,
) -> Tuple[xr.DataArray, xr.DataArray]:
    """
    将异常分布参数还原到物理单位（使用实况 GAM 气候态，Dabernig et al. 2017）。
    """
    loc = location_parameter.copy(deep=True)
    sc = scale_parameter.copy(deep=True)
    loc.values = (loc.values * truth_sd.values) + truth_mean.values
    sc.values = sc.values * truth_sd.values
    loc.attrs["units"] = truth_mean.attrs.get("units", "1")
    sc.attrs["units"] = truth_mean.attrs.get("units", "1")
    return loc, sc
