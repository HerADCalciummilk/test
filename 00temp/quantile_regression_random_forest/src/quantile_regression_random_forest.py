"""用分位数回归随机森林订正集合预报。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quantile_regression_random_forest.src.features import (
    apply_transformation,
    check_transformation,
    drop_incomplete_rows,
    prep_features_from_config,
    reverse_transformation,
    sanitise_forecast_frame,
)
from quantile_regression_random_forest.src._quantile_forest import RandomForestQuantileRegressor
from quantile_regression_random_forest.util.frames import (
    as_truth_frame,
    combine_forecasts,
    default_site_keys,
    group_keys,
    predictions_to_grid,
    predictions_to_station,
)


class TrainQuantileRegressionRandomForests:
    """训练分位数回归随机森林。"""

    def __init__(
        self,
        target_name: str,
        feature_config: dict[str, list[str]],
        n_estimators: int = 100,
        max_depth: int | None = None,
        max_samples: float | int | None = None,
        random_state: int | None = None,
        transformation: str | None = None,
        pre_transform_addition: float = 0,
        unique_site_id_keys: list[str] | str | None = None,
        valid_forecast_proportion: float = 0.5,
        **kwargs: Any,
    ) -> None:
        check_transformation(transformation)
        self.target_name = target_name
        self.feature_config = feature_config
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.max_samples = max_samples
        self.random_state = random_state
        self.transformation = transformation
        self.pre_transform_addition = float(pre_transform_addition)
        self.unique_site_id_keys = unique_site_id_keys
        self.valid_forecast_proportion = valid_forecast_proportion
        self.model_kwargs = kwargs

    def process(self, forecast, truth) -> dict:
        """用历史预报和对应实况训练模型。

        forecast、truth 可以是 meteva 格点，也可以是 meteva 站点表。
        格点按 lat/lon 当成站点，member 是集合成员。
        """
        forecast_frame = combine_forecasts(forecast)
        truth_frame = as_truth_frame(truth)
        self._check_same_kind(forecast_frame, truth_frame)
        site_keys = self._site_keys(forecast_frame)
        forecast_frame = self._transform_target(forecast_frame)
        truth_frame = truth_frame.copy()
        truth_frame["ob_value"] = apply_transformation(
            truth_frame["ob_value"], self.transformation, self.pre_transform_addition
        )
        keys = group_keys(forecast_frame, site_keys)
        forecast_frame, feature_columns = prep_features_from_config(
            forecast_frame,
            self.feature_config,
            keys,
            transformation=self.transformation,
            pre_transform_addition=self.pre_transform_addition,
        )
        merge_columns = [*site_keys, "level", "valid_time"]
        forecast_frame = drop_incomplete_rows(
            forecast_frame,
            merge_columns + feature_columns,
            self.valid_forecast_proportion,
        )
        forecast_frame = sanitise_forecast_frame(forecast_frame, self.feature_config, keys)
        truth_values = (
            truth_frame[merge_columns + ["ob_value"]]
            .groupby(merge_columns, as_index=False, sort=False)["ob_value"]
            .mean()
        )
        combined = forecast_frame.merge(truth_values, on=merge_columns, how="inner")
        if combined.empty:
            raise ValueError("预报和实况没有相同站点和有效时间的匹配样本")
        model = RandomForestQuantileRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            max_samples=self.max_samples,
            random_state=self.random_state,
            **self.model_kwargs,
        )
        model.fit(combined[feature_columns].to_numpy(dtype=np.float64), combined["ob_value"].to_numpy())
        return {
            "model": model,
            "target_name": self.target_name,
            "feature_config": self.feature_config,
            "transformation": self.transformation,
            "pre_transform_addition": self.pre_transform_addition,
            "unique_site_id_keys": site_keys,
            "feature_column_names": feature_columns,
        }

    def _transform_target(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.target_name not in frame.columns:
            raise ValueError(f"预报数据中没有目标变量 {self.target_name}")
        frame = frame.copy()
        frame[self.target_name] = apply_transformation(
            frame[self.target_name], self.transformation, self.pre_transform_addition
        )
        return frame

    def _site_keys(self, frame: pd.DataFrame) -> list[str]:
        if self.unique_site_id_keys is None:
            return default_site_keys(frame)
        if isinstance(self.unique_site_id_keys, str):
            return [self.unique_site_id_keys]
        return list(self.unique_site_id_keys)

    @staticmethod
    def _check_same_kind(forecast_frame: pd.DataFrame, truth_frame: pd.DataFrame) -> None:
        if forecast_frame.attrs.get("source_kind") != truth_frame.attrs.get("source_kind"):
            raise ValueError("预报和实况必须同为格点或同为站点")


class ApplyQuantileRegressionRandomForests:
    """用训练好的分位数回归森林输出订正分位数。"""

    def __init__(
        self,
        target_name: str | None = None,
        feature_config: dict[str, list[str]] | None = None,
        quantiles: list[float] | None = None,
        transformation: str | None = None,
        pre_transform_addition: float = 0,
        unique_site_id_keys: list[str] | str | None = None,
    ) -> None:
        check_transformation(transformation)
        self.target_name = target_name
        self.feature_config = feature_config
        self.quantiles = [0.1, 0.5, 0.9] if quantiles is None else [float(item) for item in quantiles]
        self.transformation = transformation
        self.pre_transform_addition = float(pre_transform_addition)
        self.unique_site_id_keys = unique_site_id_keys

    def process(self, model_bundle: dict, forecast):
        """返回与输入同类的订正结果。member 维或 member 列改为分位数。"""
        target_name = self.target_name or model_bundle["target_name"]
        feature_config = self.feature_config or model_bundle["feature_config"]
        transformation = model_bundle.get("transformation", self.transformation)
        addition = float(model_bundle.get("pre_transform_addition", self.pre_transform_addition))
        check_transformation(transformation)
        site_keys = self._site_keys(model_bundle)

        forecast_frame = combine_forecasts(forecast)
        source_kind = forecast_frame.attrs.get("source_kind")
        source_units = forecast_frame.attrs.get("dtime_units", "hour")
        grid_attrs = dict(forecast_frame.attrs.get("grid_attrs", {}))
        station_attrs = dict(forecast_frame.attrs.get("station_attrs", {}))
        if site_keys is None:
            site_keys = default_site_keys(forecast_frame)
        if target_name not in forecast_frame.columns:
            raise ValueError(f"预报数据中没有目标变量 {target_name}")
        forecast_frame = forecast_frame.copy()
        forecast_frame[target_name] = apply_transformation(
            forecast_frame[target_name], transformation, addition
        )
        keys = group_keys(forecast_frame, site_keys)
        forecast_frame, feature_columns = prep_features_from_config(
            forecast_frame,
            feature_config,
            keys,
            transformation=transformation,
            pre_transform_addition=addition,
        )
        expected = model_bundle.get("feature_column_names", feature_columns)
        missing = [column for column in expected if column not in feature_columns]
        if missing:
            raise ValueError(f"当前预报无法生成训练时使用的特征: {missing}")
        feature_columns = expected
        template = sanitise_forecast_frame(forecast_frame, feature_config, keys).reset_index(drop=True)
        if template[feature_columns].isnull().any().any():
            raise ValueError("应用订正时特征中存在缺测")
        predicted = np.asarray(
            model_bundle["model"].predict(
                template[feature_columns].to_numpy(dtype=np.float64),
                quantiles=self.quantiles,
            ),
            dtype=np.float64,
        )
        if predicted.ndim == 1:
            predicted = predicted.reshape(-1, 1)
        predicted = reverse_transformation(predicted, transformation, addition).astype(np.float32)
        if source_kind == "grid":
            grid_attrs["dtime_units"] = source_units
            return predictions_to_grid(template, predicted, self.quantiles, target_name, grid_attrs)
        station_attrs["dtime_units"] = source_units
        return predictions_to_station(template, predicted, self.quantiles, target_name, station_attrs)

    def _site_keys(self, model_bundle: dict) -> list[str] | None:
        if self.unique_site_id_keys is None:
            stored = model_bundle.get("unique_site_id_keys")
            return None if stored is None else list(stored)
        if isinstance(self.unique_site_id_keys, str):
            return [self.unique_site_id_keys]
        return list(self.unique_site_id_keys)


def train_qrf(forecast, truth, feature_config: dict[str, list[str]], target_name: str, **kwargs) -> dict:
    """训练并返回可 pickle 的模型包。"""
    return TrainQuantileRegressionRandomForests(
        target_name=target_name,
        feature_config=feature_config,
        **kwargs,
    ).process(forecast, truth)


def apply_qrf(model_bundle: dict, forecast, quantiles: list[float] | None = None, **kwargs):
    """应用模型。输出格点或站点表，member 表示分位数。"""
    return ApplyQuantileRegressionRandomForests(quantiles=quantiles, **kwargs).process(
        model_bundle, forecast
    )
