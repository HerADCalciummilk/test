# -*- coding: utf-8 -*-
"""用分位数回归随机森林订正集合预报。

``command`` 为 train 或 apply。预报文件多个时用逗号分隔。
``python -m cli train forecast=... truth=...``
``python -m quantile_regression_random_forest command=apply forecast=... model=...``
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_PARENT, _ROOT_DIR):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

from utils.merge_params import merge_params

_TESTDATA = Path(_ROOT_DIR) / "testdata"


def _split(text):
    if text is None or text == "":
        return None
    if isinstance(text, (list, tuple)):
        return [str(item).strip() for item in text if str(item).strip()]
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _paths(text, default):
    found = _split(text)
    if found:
        return found
    return [str(default)]


def _load_many(paths, names):
    from quantile_regression_random_forest.util.meteva_data import load_meteva

    loaded = [load_meteva(path) for path in paths]
    if names:
        if len(names) != len(loaded):
            raise ValueError("var_names 的数量需要和预报文件数量一致")
        for item, name in zip(loaded, names):
            if hasattr(item, "name"):
                item.name = name
    if len(loaded) == 1:
        return loaded[0]
    return loaded


def _read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _quantiles(text):
    parts = _split(text) or ["0.1", "0.5", "0.9"]
    return [float(item) for item in parts]


def _default_output(forecast_path: str) -> Path:
    suffix = Path(forecast_path).suffix.lower()
    if suffix in {".nc", ".nc4"}:
        return Path("quantile_regression_random_forest_calibrated.nc")
    return Path("quantile_regression_random_forest_calibrated.csv")


@merge_params()
def process(
    command: str = None,
    forecast: str = None,
    truth: str = None,
    feature_config: str = None,
    target: str = None,
    var_names: str = None,
    output: str = None,
    n_estimators: int = 100,
    max_depth: int = None,
    max_samples: float = None,
    max_features: float = None,
    random_state: int = 0,
    transformation: str = None,
    pre_transform_addition: float = 0.0,
    site_keys: str = None,
    model: str = None,
    quantiles: str = None,
    config=None,
):
    """读 meteva 数据，调用插件训练或订正，再写出。"""
    _ = config
    from quantile_regression_random_forest.src.quantile_regression_random_forest_plugin import (
        QuantileRegressionRandomForestPlugin,
    )
    from quantile_regression_random_forest.util.meteva_data import load_meteva, save_meteva

    name = (command or "").strip().lower()
    if name not in ("train", "apply", "predict"):
        raise ValueError("缺少 command。请传 train 或 apply")
    forecast_paths = _paths(forecast, _TESTDATA / "forecast_sta.csv")
    # 读入预报；训练时再读实况
    forecasts = _load_many(forecast_paths, _split(var_names))
    plugin = QuantileRegressionRandomForestPlugin()
    site = _split(site_keys)
    if name == "train":
        truth_path = truth or str(_TESTDATA / "truth_sta.csv")
        config_path = feature_config or str(_TESTDATA / "feature_config.json")
        bundle = plugin.process(
            "train",
            forecasts,
            truth=load_meteva(truth_path),
            feature_config=_read_json(config_path),
            target_name=target or "air_temperature",
            n_estimators=n_estimators,
            max_depth=max_depth,
            max_samples=max_samples,
            max_features=max_features,
            random_state=random_state,
            transformation=transformation,
            pre_transform_addition=pre_transform_addition,
            site_keys=site,
        )
        output_path = Path(output or "quantile_regression_random_forest_model.pkl")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as handle:
            pickle.dump(bundle, handle)
        print("已写出模型 %s" % output_path)
        return 0

    model_path = Path(model or "quantile_regression_random_forest_model.pkl")
    if not model_path.is_file():
        raise FileNotFoundError(
            "找不到模型文件 %s，请先运行 command=train" % model_path
        )
    with model_path.open("rb") as handle:
        bundle = pickle.load(handle)
    feature = _read_json(feature_config) if feature_config else None
    result = plugin.process(
        "apply",
        forecasts,
        model_bundle=bundle,
        quantiles=_quantiles(quantiles),
        target_name=target,
        feature_config=feature,
        site_keys=site,
    )
    output_path = Path(output) if output else _default_output(forecast_paths[0])
    save_meteva(result, output_path)
    print("已写出订正结果 %s" % output_path)
    return 0
