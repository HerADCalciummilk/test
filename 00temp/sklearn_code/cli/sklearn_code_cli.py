# -*- coding: utf-8 -*-
"""sklearn 回归 / 分类：按需训练后预测并写出结果。

在 ``00temp`` 下执行 ``python -m sklearn_code``，或包内 ``python -m cli``。
``@merge_params`` 合参；一条任务是一次「加载/训练 → 预测 → 落盘」。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Union

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_PARENT = os.path.dirname(_ROOT_DIR)
for _p in (_ROOT_DIR, _SRC_DIR, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib
import pandas as pd

from sklearn_plugin import SklearnCal
from utils.merge_params import merge_params


def _abs_path(path: Optional[str]) -> Optional[str]:
    if path is None:
        return None
    text = str(path).strip()
    if not text:
        return None
    text = os.path.expanduser(text)
    if os.path.isabs(text):
        return os.path.normpath(text)
    return os.path.normpath(os.path.join(_ROOT_DIR, text))


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _as_dict(value: Any) -> dict:
    if value is None or value is False:
        return {}
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("超参数须为 JSON 对象，收到: %r" % (value,)) from exc
    if not isinstance(parsed, dict):
        raise ValueError("超参数 JSON 必须是对象，收到: %r" % (value,))
    return parsed


def _as_optional_name(value: Any) -> Optional[Union[str, object]]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


def _run_sklearn_job(cfg: dict):
    """一次训练（按需）+ 预测 + 写出。"""
    train_path = cfg["train_path"]
    predict_path = cfg["predict_path"]
    model_save_path = cfg["model_save_path"]
    output_path = cfg["output_path"]
    feature_cols = cfg["feature_cols"]
    target_col = cfg["target_col"]
    data_name = cfg["data_name"]
    model = cfg["model"]
    model_kwargs = cfg["model_kwargs"]
    feat_model = cfg["feat_model"]
    feat_kwargs = cfg["feat_kwargs"]
    retrain = bool(cfg["retrain"])

    if not Path(predict_path).is_file():
        raise FileNotFoundError("预测特征文件不存在：%s" % predict_path)

    model_file = Path(model_save_path)
    if retrain or not model_file.is_file():
        if not Path(train_path).is_file():
            raise FileNotFoundError("训练数据文件不存在：%s" % train_path)
        print("读取训练文件：%s" % train_path)
        train_df = pd.read_csv(train_path, parse_dates=["time"])
        cal = SklearnCal(
            model=model,
            model_kwargs=model_kwargs,
            feat_model=feat_model,
            feat_kwargs=feat_kwargs,
        )
        estimator = cal.process(
            train_df,
            feature_cols=feature_cols,
            target_col=target_col,
            mode="train",
        )
        if estimator is None:
            raise ValueError("训练失败：有效样本不足 2 个或模型拟合失败")
        model_file.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(estimator, model_file)
        print("模型已保存：%s" % model_file)
    else:
        print("加载已有模型：%s" % model_file)
        cal = SklearnCal(estimator=joblib.load(model_file))

    print("读取预测特征：%s" % predict_path)
    predict_df = pd.read_csv(predict_path, parse_dates=["time"])
    print("开始预测 ...")
    result = cal.process(
        predict_df,
        feature_cols=feature_cols,
        mode="predict",
        data_name=data_name,
    )
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    print("预测完成，结果已保存：%s" % out_path)
    return result


@merge_params()
def process(
    train_path: str = None,
    predict_path: str = None,
    model_save_path: str = None,
    output_path: str = None,
    feature_cols: list = None,
    target_col: str = None,
    data_name: str = None,
    model: str = None,
    model_kwargs: str = None,
    feat_model: str = None,
    feat_kwargs: str = None,
    retrain: bool = None,
    config=None,
):
    """主入口。``config`` 只换配置文件。"""
    _ = config
    # 签名预设（ini 未覆盖时使用；与 resource/conf.ini 对齐）
    if train_path is None:
        train_path = "resource/data/train_data.txt"
    if predict_path is None:
        predict_path = "resource/data/predict_data.txt"
    if model_save_path is None:
        model_save_path = "resource/model/model.pkl"
    if output_path is None:
        output_path = "resource/prediction/prediction.txt"
    if target_col is None:
        target_col = "TEM"
    if data_name is None:
        data_name = "TEM_pred"
    if model is None:
        model = "linear"
    if retrain is None:
        retrain = False

    train_path = _abs_path(train_path)
    predict_path = _abs_path(predict_path)
    model_save_path = _abs_path(model_save_path)
    output_path = _abs_path(output_path)
    cols = _as_str_list(feature_cols)
    if not cols:
        cols = ["TEM", "PRE_1h", "PRE_3h", "PRE_6h"]
    if not train_path:
        raise ValueError("缺少参数: train_path")
    if not predict_path:
        raise ValueError("缺少参数: predict_path")
    if not model_save_path:
        raise ValueError("缺少参数: model_save_path")
    if not output_path:
        raise ValueError("缺少参数: output_path")
    if not target_col:
        raise ValueError("缺少参数: target_col")

    cfg = {
        "train_path": train_path,
        "predict_path": predict_path,
        "model_save_path": model_save_path,
        "output_path": output_path,
        "feature_cols": cols,
        "target_col": str(target_col).strip(),
        "data_name": str(data_name).strip() or "prediction",
        "model": _as_optional_name(model) or "linear",
        "model_kwargs": _as_dict(model_kwargs),
        "feat_model": _as_optional_name(feat_model),
        "feat_kwargs": _as_dict(feat_kwargs),
        "retrain": bool(retrain),
    }
    return _run_sklearn_job(cfg)
