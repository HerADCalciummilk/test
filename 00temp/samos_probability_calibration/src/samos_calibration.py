"""
SAMOS 对外 API：组合 GAM 气候态与 EMOS 异常订正。

  train_gams (gam_calibration) → 预测气候均值/标准差 → 标准化异常 → train_emos (emos)
  应用：GAM 气候态 → 异常 → apply_emos(return_parameters) → 实况气候态还原 → 分布预报
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

import numpy as np
import xarray as xr

from emos_calibration import apply_emos, train_emos
from emos_core import (
    convert_to_realizations,
    generate_forecast_from_distribution,
    get_attribute_from_coefficients,
)
from emos_grid import (
    GRID_DTIME_DIM,
    GRID_LAT_DIM,
    GRID_LEVEL_DIM,
    GRID_LON_DIM,
    GRID_MEMBER_DIM,
    GRID_TIME_DIM,
    GridInput,
    ensure_dtime_dimension,
    forecast_to_grid,
    levels_to_process,
    merge_level_forecasts,
    normalize_grid_input,
    scatter_spot_coeff_to_lat_lon,
    select_level,
    stack_lat_lon_to_spot,
    to_internal_apply,
    to_internal_percentile_forecast,
    to_internal_prob_template,
    unstack_spot_to_lat_lon,
    validate_grid_format,
)
from emos_xr_utils import (
    REALIZATION_DIM,
    SPOT_DIM,
    TIME_DIM,
    get_bounds_of_distribution,
    get_forecast_type,
)
from gam_calibration import GAMModels, train_gams
from gam_grid import (
    calculate_climate_anomalies,
    get_climatological_stats,
    normalize_gam_fields,
    normalize_gam_input,
    transform_anomalies_to_original_units,
)

InputField = GridInput


def train_samos(
    historic_forecasts: InputField,
    truths: InputField,
    forecast_gams: GAMModels,
    truth_gams: GAMModels,
    gam_features: Sequence[str],
    gam_additional_fields: Optional[Sequence[InputField]] = None,
    emos_additional_fields: Optional[Sequence[InputField]] = None,
    *,
    distribution: str = "norm",
    emos_kwargs: Optional[dict] = None,
    var_name: str | None = None,
    levels: Optional[Sequence[float]] = None,
    **trainer_kwargs: Any,
) -> xr.Dataset:
    """
    在标准化异常上训练 EMOS 系数（调用 ``emos_calibration.train_emos``）。

    ``forecast_gams`` / ``truth_gams`` 由 ``gam_calibration.train_gams`` 分别对预报、实况拟合；
    ``gam_features`` / ``gam_additional_fields`` 须与训练 GAM 时一致（静态因子放这里）。

    默认 ``emos_additional_fields=None``：异常空间 EMOS 按点/站一维系数（β 仅集合均值），
    不再把海拔等静态场当作 EMOS 预测因子；需要时才显式传入。
    """
    hf = normalize_gam_input(historic_forecasts, var_name=var_name)
    tr = normalize_gam_input(truths, var_name=var_name)
    gam_add = normalize_gam_fields(gam_additional_fields, var_name=var_name)

    forecast_mean, forecast_sd = get_climatological_stats(
        hf, forecast_gams, gam_features, gam_add
    )
    truth_mean, truth_sd = get_climatological_stats(
        tr, truth_gams, gam_features, gam_add
    )
    forecast_ca = calculate_climate_anomalies(hf, forecast_mean, forecast_sd)
    truth_ca = calculate_climate_anomalies(tr, truth_mean, truth_sd)

    emos_kw = dict(emos_kwargs or {})
    emos_kw.setdefault("distribution", distribution)
    emos_kw.update(trainer_kwargs)

    return train_emos(
        forecast_ca,
        truth_ca,
        additional_fields=emos_additional_fields,
        var_name=var_name,
        levels=levels,
        **emos_kw,
    )


def _forecast_to_internal_realizations(
    fc_level: xr.DataArray,
    additional_fields: Optional[List[xr.DataArray]],
    *,
    realizations_count: int | None,
    ignore_ecc_bounds: bool,
    prob_template: xr.DataArray | None,
) -> tuple[xr.DataArray, np.timedelta64, xr.DataArray]:
    """六维订正切片 → 带 realization 的内部格式及输出模板。"""
    ftype = get_forecast_type(fc_level)

    if ftype == "percentiles":
        fc_internal = to_internal_percentile_forecast(fc_level)
        fp = fc_internal["forecast_period"].values
        output_template = fc_internal
    elif prob_template is not None:
        fc_internal, _, fp = to_internal_apply(fc_level, additional_fields)
        output_template = to_internal_prob_template(prob_template, fp)
    else:
        fc_internal, _, fp = to_internal_apply(fc_level, additional_fields)
        output_template = fc_internal

    if ftype != "realizations":
        if not realizations_count:
            raise ValueError(
                f"realizations_count required when forecast type is {ftype!r}."
            )
        fc_internal = convert_to_realizations(
            fc_internal, realizations_count, ignore_ecc_bounds
        )
        # Probabilities: swap template to thresholds. Percentiles: keep the
        # pre-conversion percentile template (do not use realizations).
        if prob_template is not None:
            output_template = to_internal_prob_template(prob_template, fp)

    return fc_internal, fp, output_template


def _internal_to_samos_grid(
    internal: xr.DataArray,
    template_level: xr.DataArray,
) -> xr.DataArray:
    """内部 realization 格式 → 六维命名（供 GAM / 异常计算）。"""
    da = internal.copy(deep=True)
    if REALIZATION_DIM in da.dims:
        da = da.rename({REALIZATION_DIM: GRID_MEMBER_DIM})
    if TIME_DIM in da.dims:
        da = da.rename({TIME_DIM: GRID_TIME_DIM})

    if SPOT_DIM in da.dims:
        lat = np.unique(np.asarray(template_level[GRID_LAT_DIM].values))
        lon = np.unique(np.asarray(template_level[GRID_LON_DIM].values))
        drop = [c for c in (GRID_LAT_DIM, GRID_LON_DIM) if c in da.coords]
        if drop:
            da = da.drop_vars(drop)
        if int(da.sizes[SPOT_DIM]) == len(lat) * len(lon):
            da = unstack_spot_to_lat_lon(da, lat, lon)
        else:
            da = scatter_spot_coeff_to_lat_lon(da, lat, lon)

    if GRID_DTIME_DIM not in da.dims and GRID_DTIME_DIM in template_level.dims:
        da = da.expand_dims({GRID_DTIME_DIM: template_level[GRID_DTIME_DIM].values})
    if GRID_LEVEL_DIM not in da.dims and GRID_LEVEL_DIM in template_level.dims:
        da = da.expand_dims({GRID_LEVEL_DIM: template_level[GRID_LEVEL_DIM].values})

    da.name = template_level.name
    da.attrs.update(template_level.attrs)
    return da


def _climatology_for_parameters(
    climatology: xr.DataArray,
    parameters: xr.DataArray,
    fc_internal: xr.DataArray,
) -> xr.DataArray:
    """将六维气候态对齐到 EMOS 参数的空间/时间维。"""
    work = climatology.copy(deep=True)
    for dim in (GRID_MEMBER_DIM, GRID_LEVEL_DIM, GRID_DTIME_DIM):
        if dim in work.dims:
            work = work.isel({dim: 0}, drop=True)
    if GRID_TIME_DIM in work.dims:
        work = work.rename({GRID_TIME_DIM: TIME_DIM})

    if SPOT_DIM in fc_internal.dims and GRID_LAT_DIM in work.dims:
        work = stack_lat_lon_to_spot(work)
        work = work.sel({SPOT_DIM: fc_internal[SPOT_DIM].values})

    aligned, _ = xr.align(work, parameters, join="outer")
    return aligned


def apply_samos(
    forecast: InputField,
    forecast_gams: GAMModels,
    truth_gams: GAMModels,
    emos_coefficients: xr.Dataset,
    gam_features: Sequence[str],
    gam_additional_fields: Optional[Sequence[InputField]] = None,
    emos_additional_fields: Optional[Sequence[InputField]] = None,
    prob_template: Optional[InputField] = None,
    *,
    var_name: str | None = None,
    levels: Optional[Sequence[float]] = None,
    realizations_count: int | None = None,
    ignore_ecc_bounds: bool = True,
    tolerate_time_mismatch: bool = False,
    predictor: str = "mean",
    randomise: bool = False,
    random_seed: int | None = None,
    percentiles: Optional[Sequence] = None,
) -> xr.Dataset:
    """
    应用 SAMOS 订正，输出格式与输入预报类型一致（集合/概率/分位值）。

    GAM 侧 ``gam_additional_fields`` 与训练一致（静态因子）；异常 EMOS 侧默认
    ``emos_additional_fields=None``，与 ``train_samos`` 推荐用法一致。
    """
    fc = normalize_gam_input(forecast, var_name=var_name)
    fc = ensure_dtime_dimension(fc)
    validate_grid_format(fc, apply=True)

    gam_add = normalize_gam_fields(gam_additional_fields, var_name=var_name)
    emos_add = normalize_gam_fields(emos_additional_fields, var_name=var_name)
    prob = (
        normalize_grid_input(prob_template, var_name=var_name)
        if prob_template is not None
        else None
    )
    input_forecast_type = get_forecast_type(fc)
    pct_list = [float(p) for p in percentiles] if percentiles is not None else None

    level_outputs: list[xr.Dataset] = []
    for level in levels_to_process(fc, levels):
        fc_level = select_level(fc, level)
        emos_add_level = (
            [select_level(f, level) for f in emos_add] if emos_add else None
        )

        fc_internal, fp, output_template = _forecast_to_internal_realizations(
            fc_level,
            emos_add_level,
            realizations_count=realizations_count,
            ignore_ecc_bounds=ignore_ecc_bounds,
            prob_template=prob,
        )
        # Realization inputs already have six-dim lat/lon; use them for GAM/anomaly.
        # Percentile/probability inputs need conversion from internal realizations.
        if get_forecast_type(fc_level) == "realizations":
            fc_6d = fc_level
        else:
            fc_6d = _internal_to_samos_grid(fc_internal, fc_level)

        forecast_mean, forecast_sd = get_climatological_stats(
            fc_6d, forecast_gams, gam_features, gam_add
        )
        forecast_ca_6d = calculate_climate_anomalies(
            fc_6d, forecast_mean, forecast_sd
        )

        params = apply_emos(
            forecast=forecast_ca_6d,
            coefficients=emos_coefficients,
            additional_fields=emos_add,
            var_name=var_name,
            levels=[level],
            tolerate_time_mismatch=tolerate_time_mismatch,
            predictor=predictor,
            return_parameters=True,
        )
        location = params["location_parameter"]
        scale = params["scale_parameter"]

        truth_mean_6d, truth_sd_6d = get_climatological_stats(
            fc_6d, truth_gams, gam_features, gam_add
        )
        truth_mean = _climatology_for_parameters(truth_mean_6d, location, fc_internal)
        truth_sd = _climatology_for_parameters(truth_sd_6d, scale, fc_internal)
        location, scale = transform_anomalies_to_original_units(
            location, scale, truth_mean, truth_sd
        )

        distribution = {
            "name": get_attribute_from_coefficients(emos_coefficients, "distribution"),
            "location": location,
            "scale": scale,
            "shape": get_attribute_from_coefficients(
                emos_coefficients, "shape_parameters", optional=True
            ),
        }
        result = generate_forecast_from_distribution(
            distribution,
            output_template,
            pct_list,
            randomise,
            random_seed,
        )

        if input_forecast_type != "probabilities" and prob is None:
            diag_name = result.name or var_name or "air_temperature"
            bounds = get_bounds_of_distribution(
                diag_name, result.attrs.get("units", "1")
            )
            result = result.clip(min=float(bounds[0]), max=float(bounds[1]))

        level_outputs.append(
            forecast_to_grid(result, fc_level, level, fp, var_name=var_name)
        )

    return merge_level_forecasts(level_outputs)


__all__ = [
    "InputField",
    "apply_samos",
    "train_gams",
    "train_samos",
]
