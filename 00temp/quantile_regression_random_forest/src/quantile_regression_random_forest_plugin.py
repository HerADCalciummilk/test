# -*- coding: utf-8 -*-
"""分位数回归随机森林插件。训练和订正仍调用原有函数，不改模型公式。"""
from __future__ import annotations

from utils.base_plugin import BasePlugin
from quantile_regression_random_forest.src.quantile_regression_random_forest import apply_qrf, train_qrf


class QuantileRegressionRandomForestPlugin(BasePlugin):
    """包一层 ``train_qrf`` / ``apply_qrf``。"""

    def process(
        self,
        command,
        forecast,
        truth=None,
        feature_config=None,
        target_name=None,
        n_estimators=100,
        max_depth=None,
        max_samples=None,
        max_features=None,
        random_state=0,
        transformation=None,
        pre_transform_addition=0.0,
        site_keys=None,
        model_bundle=None,
        quantiles=None,
    ):
        name = str(command or "").strip().lower()
        if name == "train":
            # 只把调用方显式给出的抽样参数传进原训练函数
            kwargs = {
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "random_state": random_state,
                "transformation": transformation,
                "pre_transform_addition": pre_transform_addition,
            }
            if max_samples is not None:
                kwargs["max_samples"] = max_samples
            if max_features is not None:
                kwargs["max_features"] = max_features
            if site_keys:
                kwargs["unique_site_id_keys"] = site_keys
            return train_qrf(
                forecast,
                truth,
                feature_config=feature_config,
                target_name=target_name,
                **kwargs,
            )
        if name in ("apply", "predict"):
            kwargs = {}
            if target_name:
                kwargs["target_name"] = target_name
            if feature_config:
                kwargs["feature_config"] = feature_config
            if site_keys:
                kwargs["unique_site_id_keys"] = site_keys
            return apply_qrf(model_bundle, forecast, quantiles=quantiles, **kwargs)
        raise ValueError("command 须为 train 或 apply")
