#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""基于 scikit-learn 的单模型统计后处理插件。

插件类：SklearnCal
    以统一标准站点数据（pandas.DataFrame）为输入，在 ``process`` 中通过 ``mode``
    参数区分训练（``mode="train"``）与推理（``mode="predict"``）；回归与分类
    任务由传入的估计器类型自动判定（``sklearn.base.is_classifier``）。
    插件内部不做任何文件读写，模型持久化与数据 IO 由算法应用（CLI）层负责。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd
from sklearn.base import is_classifier
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import (
    BayesianRidge,
    LinearRegression,
    LogisticRegression,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

AVAILABLE_MODELS: Dict[str, type] = {
    "linear": LinearRegression,  # 拟合
    "random_forest": RandomForestRegressor,  # 拟合
    "bayesian": BayesianRidge,  # 拟合
    "logistic": LogisticRegression,  # 分类
    "random_forest_classifier": RandomForestClassifier,  # 分类
    "svc": SVC,  # 分类
}

AVAILABLE_FEATURES: Dict[str, type] = {
    "pca": PCA,
    "standard_scaler": StandardScaler,
}

# 统一站点数据格式（STDA）的 6 个维度列。
DIM_COLS: List[str] = ["level", "time", "dtime", "id", "lon", "lat"]

class SklearnCal:
    """sklearn 单模型训练 / 推理插件。

    通过 ``__init__`` 设置算法与超参数，通过 ``process`` 执行主功能：
    ``mode="train"`` 在训练数据上拟合单个全局估计器并缓存到 ``self.estimator``；
    ``mode="predict"`` 使用缓存（或初始化时传入）的估计器输出预测结果。
    回归与分类任务由估计器类型自动判定：回归器输出连续值，分类器输出类别标签。

    插件只处理内存中的 pandas.DataFrame，不读写文件；训练所得模型由 CLI 层
    通过 joblib 等工具持久化，推理时由 CLI 层加载后经 ``estimator`` 参数传入。
    """

    def __init__(
        self,
        model: Optional[Union[str, type, object]] = None,
        model_kwargs: Optional[dict] = None,
        feat_model: Optional[Union[str, type, object]] = None,
        feat_kwargs: Optional[dict] = None,
        estimator: Optional[object] = None,
    ) -> None:
        """初始化插件。

        Args:
            model: 算法：``AVAILABLE_MODELS`` 的键（如 ``"linear"``、
                ``"logistic"``）、sklearn 估计器类或已构造实例；
                ``mode="train"`` 时不能为 None。
            model_kwargs: 传给估计器构造的超参数字典，如 ``{"n_estimators": 50}``；
                None 视作空字典；model 为已构造实例时不允许非空。
            feat_model: 特征工程：``AVAILABLE_FEATURES`` 的键（如 ``"pca"``）、
                sklearn 变换器类或实例；None 表示不启用特征工程。
            feat_kwargs: 传给变换器构造的超参数字典，如 ``{"n_components": 4}``；
                None 视作空字典；feat_model 为已构造实例时不允许非空。
            estimator: 已拟合估计器（可选）。传入后可直接执行
                ``process(..., mode="predict")``，用于加载已保存的模型。

        Raises:
            ValueError: model_kwargs 或 feat_kwargs 不是 dict。
        """
        if model_kwargs is None:
            model_kwargs = {}
        elif not isinstance(model_kwargs, dict):
            raise ValueError("model_kwargs 必须为 dict")
        if feat_kwargs is None:
            feat_kwargs = {}
        elif not isinstance(feat_kwargs, dict):
            raise ValueError("feat_kwargs 必须为 dict")
        self.model = model
        self.model_kwargs = model_kwargs
        self.feat_model = feat_model
        self.feat_kwargs = feat_kwargs
        self.estimator = estimator

    def _fit(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        target_col: str,
    ) -> Optional[object]:
        """在全体有效样本上拟合单个全局估计器并缓存。

        Args:
            df: 训练数据 DataFrame（特征列 + 目标列）。
            feature_cols: 特征列名。
            target_col: 目标列名；回归为连续值列，分类为类别标签列
                （整数或字符串均可）。

        Returns:
            已拟合的估计器；有效样本 <2 时为 None；拟合失败时原样抛出
            sklearn 异常。

        Raises:
            ValueError: model 为 None、算法名未知，或拟合失败（原样抛出
                sklearn 异常）。
        """
        if self.model is None:
            raise ValueError("model 必须传入 sklearn 估计器类、实例或算法名")

        # 解析模型：算法名字符串 / sklearn 类 / 已构造实例
        est = self.model
        if isinstance(est, str):
            if est not in AVAILABLE_MODELS:
                raise ValueError(
                    f"未知算法名：{est!r}，可用："
                    f"{'、'.join(sorted(AVAILABLE_MODELS))}"
                )
            est = AVAILABLE_MODELS[est](**self.model_kwargs)
        elif isinstance(est, type):
            est = est(**self.model_kwargs)
        elif self.model_kwargs:
            raise ValueError("已传入实例，不允许再传入参数")

        # 由估计器类型自动判定回归 / 分类
        is_clf = is_classifier(est)
        X = np.asarray(df[feature_cols], dtype=np.float32)
        if is_clf:
            # 分类目标保留原始标签（整数或字符串）
            y = df[target_col].to_numpy()
        else:
            y = np.asarray(df[target_col], dtype=np.float32)
        # 目标或任一特征缺测（-9999.0/NaN）的样本剔除
        valid = ~np.any(np.isnan(X), axis=1) & ~np.any(X == -9999.0, axis=1)
        if np.issubdtype(y.dtype, np.number):
            y_num = y.astype(np.float64, copy=False)
            valid &= ~np.isnan(y_num) & (y_num != -9999.0)
        else:
            valid &= pd.notna(y)
        valid = np.where(valid)[0]
        if len(valid) < 2:
            self.estimator = None
            return None

        # 解析特征工程变换器，与模型组合成 Pipeline
        if self.feat_model is not None:
            transformer = self.feat_model
            if isinstance(transformer, str):
                if transformer not in AVAILABLE_FEATURES:
                    raise ValueError(
                        f"未知算法名：{transformer!r}，"
                        f"可用：{'、'.join(sorted(AVAILABLE_FEATURES))}"
                    )
                transformer = AVAILABLE_FEATURES[transformer](**self.feat_kwargs)
            elif isinstance(transformer, type):
                transformer = transformer(**self.feat_kwargs)
            elif self.feat_kwargs:
                raise ValueError("已传入实例，不允许再传入参数")
            est = Pipeline([("feature_engineering", transformer), ("model", est)])

        # 拟合失败时直接向上抛出 sklearn 的原始异常，便于定位问题
        # （如分类器误配连续目标列的 "Unknown label type: continuous"）
        est.fit(X[valid, :], y[valid])

        self.estimator = est
        return est

    def _predict(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        data_name: str,
    ) -> pd.DataFrame:
        """对特征完整的样本执行预测，返回站点 DataFrame。

        Args:
            df: 预测特征 DataFrame（无目标列）。
            feature_cols: 特征列名，须与训练时一致。
            data_name: 输出预测列列名。

        Returns:
            维度列 + 预测列的站点 DataFrame；回归预测列为 float32 连续值，
            分类预测列为类别标签（保持训练标签类型）。特征缺测
            （-9999.0/NaN）的行被剔除。

        Raises:
            ValueError: 尚未训练或未传入 estimator。
        """
        if self.estimator is None:
            raise ValueError(
                "尚未训练模型：请先以 mode='train' 调用 process，"
                "或在 __init__ 中传入已拟合的 estimator"
            )

        X = np.asarray(df[feature_cols], dtype=np.float32)
        # 与训练一致：特征缺测（-9999.0/NaN）的行剔除，只对特征完整的行预测
        valid = ~np.any(np.isnan(X), axis=1) & ~np.any(X == -9999.0, axis=1)
        is_clf = is_classifier(self.estimator)

        out = df.loc[valid, DIM_COLS].copy()
        # 统一 time 为 datetime64[ns]，保证 CSV 读回（字符串 time）可被 meteva 处理
        out["time"] = pd.to_datetime(out["time"]).astype("datetime64[ns]")
        if not valid.any():
            # 全部特征缺测：sklearn 不允许 0 样本预测，直接返回含预测列的空表
            if is_clf:
                classes = getattr(self.estimator, "classes_", None)
                dtype = classes.dtype if classes is not None else np.float32
            else:
                dtype = np.float32
            out[data_name] = np.asarray([], dtype=dtype)
        elif is_clf:
            # 分类输出预测类别标签，保持训练标签类型（整数或字符串）
            out[data_name] = np.asarray(self.estimator.predict(X[valid]))
        else:
            out[data_name] = np.asarray(
                self.estimator.predict(X[valid]), dtype=np.float32
            )
        return out

    def process(
        self,
        df: pd.DataFrame,
        feature_cols: Sequence[str],
        target_col: Optional[str] = None,
        mode: str = "train",
        data_name: str = "prediction",
    ) -> Optional[Union[object, pd.DataFrame]]:
        """执行训练或推理。

        Args:
            df: 统一站点数据 DataFrame；训练时须含特征列与目标列，
                推理时只须含特征列。
            feature_cols: 特征列名，须为 df 中存在的列。
            target_col: 目标列名，``mode="train"`` 时必填；推理时忽略。
                回归目标为连续值列，分类目标为类别标签列。
            mode: ``"train"`` 拟合单个全局估计器；``"predict"`` 使用已拟合
                （或初始化时传入）的估计器预测。
            data_name: 推理输出预测列列名，默认 ``"prediction"``。

        Returns:
            ``mode="train"``：已拟合估计器；有效样本 <2 时为 None。
            ``mode="predict"``：维度列 + 预测列的站点 DataFrame；回归为
                float32 连续值，分类为类别标签。

        Raises:
            ValueError: mode 非法、feature_cols/target_col 缺失、列不存在、
                推理时没有可用估计器，或训练拟合失败（原样抛出 sklearn 异常）。
        """
        if mode not in ("train", "predict"):
            raise ValueError(
                f"mode 必须为 train 或 predict"
            )
        if feature_cols is None:
            raise ValueError("必须显式指定 feature_cols")
        feature_cols = list(feature_cols)

        if mode == "train":
            if target_col is None:
                raise ValueError("mode='train' 时必须显式指定 target_col")
            missing = [c for c in feature_cols + [target_col] if c not in df.columns]
            if missing:
                raise ValueError(f"列不存在：{missing}；可用列：{list(df.columns)}")
            return self._fit(df, feature_cols, target_col)

        missing = [c for c in feature_cols + DIM_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"列不存在：{missing}；可用列：{list(df.columns)}")
        return self._predict(df, feature_cols, data_name)

    def __repr__(self) -> str:
        """返回插件配置摘要，便于日志与调试。"""
        estimator = None if self.estimator is None else type(self.estimator).__name__
        return (
            f"<SklearnCal: model={self.model!r}, model_kwargs={self.model_kwargs}, "
            f"feat_model={self.feat_model!r}, feat_kwargs={self.feat_kwargs}, "
            f"estimator={estimator}>"
        )
