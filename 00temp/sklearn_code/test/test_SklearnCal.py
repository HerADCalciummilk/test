#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""SklearnCal 单元测试：统一 process 的训练与推理调度。"""
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import Pipeline

from sklearn_code.src.sklearn_plugin import (
    AVAILABLE_MODELS,
    DIM_COLS,
    SklearnCal,
)


FEATURE_COLS = ["feat_a", "feat_b", "feat_c"]
TARGET_COL = "target"


def sample_train_df():
    """训练样例：前 4 行有效，后 4 行分别含目标/特征缺测（-9999.0/NaN）。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, 1.0, 2.0, 3.0, 10.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, 5.0, 6.0, 20.0],
        [0, "2020-01-01", 0, "id3", 1.0, 2.0, 7.0, 8.0, 9.0, 30.0],
        [0, "2020-01-01", 0, "id4", 1.0, 2.0, 10.0, 11.0, 12.0, 40.0],
        [0, "2020-01-01", 0, "id5", 1.0, 2.0, 13.0, 14.0, 15.0, -9999.0],
        [0, "2020-01-01", 0, "id6", 1.0, 2.0, 16.0, 17.0, 18.0, np.nan],
        [0, "2020-01-01", 0, "id7", 1.0, 2.0, -9999.0, 20.0, 21.0, 50.0],
        [0, "2020-01-01", 0, "id8", 1.0, 2.0, 22.0, np.nan, 24.0, 60.0],
    ]
    return pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS + [TARGET_COL])


def sample_train_df_one_valid():
    """仅 1 个有效样本：训练应返回 None。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, 1.0, 2.0, 3.0, 10.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, 5.0, 6.0, -9999.0],
    ]
    return pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS + [TARGET_COL])


def sample_predict_df():
    """预测样例：前 2 行有效，后 2 行分别含特征 -9999.0/NaN，推理时应剔除。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, 1.0, 2.0, 3.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, 5.0, 6.0],
        [0, "2020-01-01", 0, "id3", 1.0, 2.0, -9999.0, 8.0, 9.0],
        [0, "2020-01-01", 0, "id4", 1.0, 2.0, 10.0, np.nan, 12.0],
    ]
    return pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS)


def sample_train_clf_df():
    """二分类训练样例：前 4 行有效（标签 0/1），后 2 行目标缺测。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, 1.0, 2.0, 3.0, 0.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, 5.0, 6.0, 0.0],
        [0, "2020-01-01", 0, "id3", 1.0, 2.0, 7.0, 8.0, 9.0, 1.0],
        [0, "2020-01-01", 0, "id4", 1.0, 2.0, 10.0, 11.0, 12.0, 1.0],
        [0, "2020-01-01", 0, "id5", 1.0, 2.0, 13.0, 14.0, 15.0, -9999.0],
        [0, "2020-01-01", 0, "id6", 1.0, 2.0, 16.0, 17.0, 18.0, np.nan],
    ]
    return pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS + [TARGET_COL])


def trained_estimator():
    """训练一个简单线性估计器，供推理测试使用。"""
    X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32)
    y = np.array([10.0, 20.0], dtype=np.float32)
    return LinearRegression().fit(X, y)


def trained_classifier():
    """训练一个简单逻辑回归分类器，供分类推理测试使用。"""
    X = np.array(
        [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]],
        dtype=np.float32,
    )
    y = np.array([0, 0, 1, 1])
    return LogisticRegression().fit(X, y)


# ---- 初始化 ----
def test_init_kwargs_must_be_dict():
    """model_kwargs 或 feat_kwargs 非 dict 时初始化抛 ValueError。"""
    with pytest.raises(ValueError):
        SklearnCal(model="linear", model_kwargs="oops")
    with pytest.raises(ValueError):
        SklearnCal(model="linear", feat_kwargs="oops")


def test_repr():
    """repr 字符串包含插件类名与状态。"""
    plugin = SklearnCal(model="linear")
    assert "SklearnCal" in repr(plugin)
    assert "estimator=None" in repr(plugin)


# ---- 训练（mode="train"）----
def test_train_returns_fitted_estimator_and_caches():
    """训练返回已拟合估计器，并缓存到实例供后续推理使用。"""
    plugin = SklearnCal(model="linear")
    est = plugin.process(
        sample_train_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    assert isinstance(est, LinearRegression)
    assert plugin.estimator is est


def test_train_insufficient_samples_returns_none():
    """有效样本不足 2 个时训练返回 None，且不保留旧模型。"""
    plugin = SklearnCal(model="linear", estimator=trained_estimator())
    assert (
        plugin.process(
            sample_train_df_one_valid(), feature_cols=FEATURE_COLS,
            target_col=TARGET_COL, mode="train",
        )
        is None
    )
    assert plugin.estimator is None


def test_train_model_none_raises():
    """model 为 None 时训练抛出 ValueError。"""
    plugin = SklearnCal(model=None)
    with pytest.raises(ValueError):
        plugin.process(
            sample_train_df(), feature_cols=FEATURE_COLS,
            target_col=TARGET_COL, mode="train",
        )


def test_train_requires_target_col():
    """训练缺少 target_col 时抛出 ValueError。"""
    plugin = SklearnCal(model="linear")
    with pytest.raises(ValueError):
        plugin.process(sample_train_df(), feature_cols=FEATURE_COLS, mode="train")


def test_train_missing_column_raises():
    """传入不存在的特征列或目标列时抛出 ValueError。"""
    plugin = SklearnCal(model="linear")
    with pytest.raises(ValueError):
        plugin.process(
            sample_train_df(), feature_cols=["no_such_col"],
            target_col=TARGET_COL, mode="train",
        )
    with pytest.raises(ValueError):
        plugin.process(
            sample_train_df(), feature_cols=FEATURE_COLS,
            target_col="no_such_col", mode="train",
        )


def test_train_unknown_model_name_raises():
    """未知算法名字符串导致训练抛出 ValueError。"""
    plugin = SklearnCal(model="no_such_algo")
    with pytest.raises(ValueError):
        plugin.process(
            sample_train_df(), feature_cols=FEATURE_COLS,
            target_col=TARGET_COL, mode="train",
        )


def test_train_model_instance_works():
    """直接传入估计器实例也能正常拟合。"""
    plugin = SklearnCal(model=LinearRegression())
    est = plugin.process(
        sample_train_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    assert isinstance(est, LinearRegression)


def test_train_model_instance_with_kwargs_raises():
    """已传实例再配 kwargs 时训练抛出 ValueError。"""
    plugin = SklearnCal(
        model=LinearRegression(), model_kwargs={"fit_intercept": False}
    )
    with pytest.raises(ValueError):
        plugin.process(
            sample_train_df(), feature_cols=FEATURE_COLS,
            target_col=TARGET_COL, mode="train",
        )


def test_train_feat_model_builds_pipeline():
    """feat_model 非 None 时训练返回包含特征工程的 Pipeline。"""
    plugin = SklearnCal(model="linear", feat_model="pca")
    est = plugin.process(
        sample_train_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    assert isinstance(est, Pipeline)
    assert [step[0] for step in est.steps] == ["feature_engineering", "model"]


@pytest.mark.parametrize("name", ["random_forest", "bayesian"])
def test_train_other_models(name):
    """random_forest 与 bayesian 算法名均能正常返回已拟合估计器。"""
    plugin = SklearnCal(model=name)
    est = plugin.process(
        sample_train_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    assert est is not None
    assert name in AVAILABLE_MODELS


# ---- 推理（mode="predict"）----
def test_predict_after_train_returns_dims_and_prediction():
    """同一实例训练后可直接推理，输出维度列+预测列并剔除特征缺测行。"""
    plugin = SklearnCal(model="linear")
    plugin.process(
        sample_train_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert list(out.columns) == DIM_COLS + ["prediction"]
    assert not set(FEATURE_COLS) & set(out.columns)  # 输出不含特征列
    assert len(out) == 2  # 缺测两行被剔除
    assert out["prediction"].dtype == np.float32
    assert pd.api.types.is_datetime64_dtype(out["time"])


def test_predict_with_init_estimator():
    """初始化时传入已拟合估计器，可直接推理。"""
    plugin = SklearnCal(estimator=trained_estimator())
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert len(out) == 2


def test_predict_without_estimator_raises():
    """未训练且未传入 estimator 时推理抛出 ValueError。"""
    plugin = SklearnCal(model="linear")
    with pytest.raises(ValueError):
        plugin.process(
            sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
        )


def test_predict_custom_data_name():
    """data_name 自定义时预测列使用该名称而非默认 prediction。"""
    plugin = SklearnCal(estimator=trained_estimator())
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS,
        mode="predict", data_name="my_pred",
    )
    assert "my_pred" in out.columns
    assert "prediction" not in out.columns


def test_predict_missing_dims_raises():
    """预测数据缺少维度列时抛出 ValueError。"""
    df = sample_predict_df().drop(columns=["lat"])
    plugin = SklearnCal(estimator=trained_estimator())
    with pytest.raises(ValueError):
        plugin.process(df, feature_cols=FEATURE_COLS, mode="predict")


def test_predict_all_missing_returns_empty():
    """全部行特征缺测时返回空表而非调用 estimator.predict。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, -9999.0, 2.0, 3.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, np.nan, 6.0],
    ]
    df = pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS)
    plugin = SklearnCal(estimator=trained_estimator())
    out = plugin.process(df, feature_cols=FEATURE_COLS, mode="predict")
    assert len(out) == 0


# ---- 调度参数校验 ----
def test_invalid_mode_raises():
    """mode 非 train/predict 时抛出 ValueError。"""
    plugin = SklearnCal(estimator=trained_estimator())
    with pytest.raises(ValueError):
        plugin.process(sample_predict_df(), feature_cols=FEATURE_COLS, mode="fit")


def test_feature_cols_required():
    """feature_cols 缺失时抛出 ValueError。"""
    plugin = SklearnCal(estimator=trained_estimator())
    with pytest.raises(ValueError):
        plugin.process(sample_predict_df(), feature_cols=None, mode="predict")


# ---- 分类任务（由估计器类型自动判定）----
@pytest.mark.parametrize("name", ["logistic", "random_forest_classifier", "svc"])
def test_train_classifier_models(name):
    """logistic / random_forest_classifier / svc 分类算法名均能正常训练。"""
    plugin = SklearnCal(model=name)
    est = plugin.process(
        sample_train_clf_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    assert est is not None
    assert name in AVAILABLE_MODELS


def test_predict_classifier_outputs_labels():
    """分类推理输出维度列 + 类别标签列，且剔除特征缺测行。"""
    plugin = SklearnCal(model="logistic")
    plugin.process(
        sample_train_clf_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS,
        mode="predict", data_name="rain_pred",
    )
    assert list(out.columns) == DIM_COLS + ["rain_pred"]
    assert len(out) == 2
    assert set(out["rain_pred"]) <= {0.0, 1.0}


def test_regression_or_classification_auto_detected():
    """同一份整数标签数据：线性回归输出 float32 连续值，逻辑回归输出类别标签。"""
    reg = SklearnCal(model="linear")
    reg.process(
        sample_train_clf_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    reg_out = reg.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert reg_out["prediction"].dtype == np.float32

    clf = SklearnCal(model=LogisticRegression())
    clf.process(
        sample_train_clf_df(), feature_cols=FEATURE_COLS,
        target_col=TARGET_COL, mode="train",
    )
    clf_out = clf.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert set(clf_out["prediction"]) <= {0.0, 1.0}


def test_predict_init_classifier_estimator_auto_detected():
    """初始化传入已拟合分类器时，推理自动按分类输出标签。"""
    plugin = SklearnCal(estimator=trained_classifier())
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert len(out) == 2
    assert set(out["prediction"]) <= {0, 1}


def test_classifier_string_labels():
    """分类标签为字符串时同样可训练并输出字符串标签。"""
    df = sample_train_clf_df().copy()
    df[TARGET_COL] = df[TARGET_COL].map({0.0: "no_rain", 1.0: "rain"})
    plugin = SklearnCal(model="logistic")
    plugin.process(
        df, feature_cols=FEATURE_COLS, target_col=TARGET_COL, mode="train"
    )
    out = plugin.process(
        sample_predict_df(), feature_cols=FEATURE_COLS, mode="predict"
    )
    assert set(out["prediction"]) <= {"no_rain", "rain"}


def test_predict_classifier_all_missing_returns_empty():
    """分类推理全部特征缺测时返回空表，预测列仍存在。"""
    rows = [
        [0, "2020-01-01", 0, "id1", 1.0, 2.0, -9999.0, 2.0, 3.0],
        [0, "2020-01-01", 0, "id2", 1.0, 2.0, 4.0, np.nan, 6.0],
    ]
    df = pd.DataFrame(rows, columns=DIM_COLS + FEATURE_COLS)
    plugin = SklearnCal(estimator=trained_classifier())
    out = plugin.process(df, feature_cols=FEATURE_COLS, mode="predict")
    assert len(out) == 0
    assert "prediction" in out.columns


def test_train_fit_error_propagates():
    """拟合失败时原样抛出 sklearn 异常，而非吞掉返回 None。"""
    df = sample_train_df().copy()
    # 连续小数目标：分类器会报 "Unknown label type: continuous"
    df[TARGET_COL] = [20.6, 13.1, 24.8, 15.3, -9999.0, np.nan, 18.2, 27.9]
    plugin = SklearnCal(model="logistic")
    with pytest.raises(ValueError, match="continuous"):
        plugin.process(
            df, feature_cols=FEATURE_COLS,
            target_col=TARGET_COL, mode="train",
        )
