"""
EMOS 对外 API：统一六维输入（格点 xarray 或站点/格点六列 DataFrame）。

维度约定（member, level, time, dtime, lat, lon）：
  - 格点：六维 xarray（meteva 语义）
  - 站点：六列 DataFrame，相同 (lat, lon) 视为同一站点
  - 预报 time=起报时间，实况 time=有效时间；实况 dtime=0

level 循环在本模块完成；内部逐层调用 grid 适配器与 EMOS 核心。
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

import xarray as xr

from emos_core import ApplyEMOS, EstimateCoefficientsForEnsembleCalibration
from emos_grid import (
    GRID_LAT_DIM,
    GRID_LON_DIM,
    AdditionalFields,
    GridInput,
    apply_level_emos,
    attach_training_station_metadata,
    check_coefficients_match_forecast,
    create_prob_template_from_grid,
    ensure_dtime_dimension,
    levels_to_process,
    merge_level_coefficients,
    merge_level_forecasts,
    normalize_grid_input,
    normalize_grid_inputs,
    train_level_emos,
    validate_apply_inputs,
    validate_grid_format,
    validate_grid_inputs,
)

InputField = GridInput


def create_prob_template(
    forecast: InputField,
    thresholds: Sequence[float],
    thresholds_operator: str,
    diagnostic_name: Optional[str] = None,
    var_name: Optional[str] = None,
    value_col: Optional[str] = None,
) -> xr.DataArray:
    """为六维预报输入创建概率模板。"""
    fc = normalize_grid_input(forecast, var_name=var_name, value_col=value_col)
    validate_grid_format(fc, apply=True)
    fc = ensure_dtime_dimension(fc)
    return create_prob_template_from_grid(
        fc, thresholds, thresholds_operator, diagnostic_name=diagnostic_name
    )


def train_emos(
    historic_forecasts: InputField,
    truths: InputField,
    additional_fields: AdditionalFields = None,
    var_name: Optional[str] = None,
    value_col: Optional[str] = None,
    levels: Optional[Sequence[float]] = None,
    strict_training: bool = False,
    **trainer_kwargs: Any,
) -> xr.Dataset:
    """
    训练 EMOS 系数。

    输入为六维 xarray 或六列 DataFrame；逐 level 独立拟合后合并。
    """
    fo, ob, add = normalize_grid_inputs(
        historic_forecasts,
        truths,
        additional_fields=additional_fields,
        var_name=var_name,
        value_col=value_col,
    )
    fo, ob, add = validate_grid_inputs(
        fo,
        ob,
        additional_fields=add,
        strict_training=strict_training,
    )
    trainer = EstimateCoefficientsForEnsembleCalibration(**trainer_kwargs)
    lat = fo[GRID_LAT_DIM].values
    lon = fo[GRID_LON_DIM].values
    point_by_point = bool(trainer_kwargs.get("point_by_point", False))

    level_coeffs: List[xr.Dataset] = []
    for level in levels_to_process(fo, levels):
        level_coeffs.append(
            train_level_emos(fo, ob, add or [], level, trainer, lat, lon, point_by_point)
        )
    merged = merge_level_coefficients(level_coeffs)
    merged = attach_training_station_metadata(merged, fo, ob)
    merged.attrs["emos_domain"] = "grid"
    return merged


def apply_emos(
    forecast: InputField,
    coefficients: xr.Dataset,
    additional_fields: AdditionalFields = None,
    var_name: Optional[str] = None,
    value_col: Optional[str] = None,
    levels: Optional[Sequence[float]] = None,
    prob_template: Optional[InputField] = None,
    realizations_count: Optional[int] = None,
    ignore_ecc_bounds: bool = True,
    tolerate_time_mismatch: bool = False,
    predictor: str = "mean",
    randomise: bool = False,
    random_seed: Optional[int] = None,
    return_parameters: bool = False,
    percentiles: Optional[Sequence] = None,
) -> xr.Dataset:
    """对六维预报输入应用 EMOS 校准；逐 level 订正后合并。"""
    fc = normalize_grid_input(forecast, var_name=var_name, value_col=value_col)
    fc = ensure_dtime_dimension(fc)
    validate_grid_format(fc, apply=True)
    check_coefficients_match_forecast(fc, coefficients)

    add: List[xr.DataArray] | None = None
    if additional_fields:
        add = [
            normalize_grid_input(f, var_name=var_name, value_col=value_col)
            for f in additional_fields
        ]
    prob = (
        normalize_grid_input(prob_template, var_name=var_name, value_col=value_col)
        if prob_template is not None
        else None
    )
    fc, coeffs, add, prob = validate_apply_inputs(
        fc,
        coefficients,
        additional_fields=add,
        prob_template=prob,
        var_name=var_name,
    )
    applier = ApplyEMOS(percentiles=percentiles)
    level_outputs: List[xr.Dataset] = []

    for level in levels_to_process(fc, levels):
        result = apply_level_emos(
            fc,
            coeffs,
            add or [],
            level,
            applier,
            prob=prob,
            var_name=var_name,
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
        level_outputs.append(result)

    return merge_level_forecasts(level_outputs)


__all__ = [
    "AdditionalFields",
    "GridInput",
    "InputField",
    "apply_emos",
    "create_prob_template",
    "train_emos",
]
