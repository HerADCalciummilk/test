"""
GAM 对外 API：拟合气候均值/标准差模型，支持静态因子作为预测特征。

六维输入与 EMOS 一致；``additional_fields`` 按 (lat, lon) 并入长表，
``features`` 中写上静态场变量名即可作为 GAM 预测因子。
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from gam_grid import (
    calculate_grid_statistics,
    normalize_gam_fields,
    normalize_gam_input,
    prepare_data_for_gam,
    validate_gam_features,
)
from gam_models import GAMFit

GAMModels = List[Any]


def train_gams(
    input_field,
    features: Sequence[str],
    model_specification: List,
    additional_fields: Optional[Sequence] = None,
    *,
    max_iter: int = 100,
    tol: float = 0.0001,
    distribution: str = "normal",
    link: str = "identity",
    fit_intercept: bool = True,
    window_length: int = 11,
    valid_rolling_window_fraction: float = 0.5,
    var_name: str | None = None,
) -> GAMModels | None:
    """
    拟合 GAM（均值 + 标准差各一个）。

    Args:
        input_field: 历史预报或实况（六维 xarray / 六列 DataFrame）。
        features: 预测因子名列表。可为坐标（``lat``/``lon``/``dtime`` 等）
            以及 ``additional_fields`` 中静态场的变量名（如 ``altitude``、``slope``）。
            下标需与 ``model_specification`` 中的特征索引一致。
        model_specification: pyGAM 项规格，例如::

            [
                ["spline", [0], {"n_splines": 10}],   # features[0]
                ["spline", [1], {"n_splines": 10}],   # features[1]
                ["linear", [2], {}],                  # features[2] 如 altitude
            ]

        additional_fields: 静态协变量列表，按 (lat, lon) 并入训练表。
    """
    da = normalize_gam_input(input_field, var_name=var_name)
    add = normalize_gam_fields(additional_fields, var_name=var_name)

    try:
        mean_da, sd_da = calculate_grid_statistics(
            da,
            window_length=window_length,
            valid_rolling_window_fraction=valid_rolling_window_fraction,
        )
    except ValueError:
        return None

    plugin = GAMFit(
        model_specification=model_specification,
        max_iter=max_iter,
        tol=tol,
        distribution=distribution,
        link=link,
        fit_intercept=fit_intercept,
    )
    value_name = da.name or "value"
    gams: GAMModels = []
    for stat_da in (mean_da, sd_da):
        df = prepare_data_for_gam(stat_da, add)
        validate_gam_features(df, features)
        gams.append(
            plugin.process(
                df[list(features)].values,
                df[value_name].values,
            )
        )
    if None in gams:
        return None
    return gams


__all__ = [
    "GAMModels",
    "train_gams",
]
