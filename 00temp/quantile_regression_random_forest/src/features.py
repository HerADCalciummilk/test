"""把集合预报整理成分位数回归森林使用的特征。"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAYS_IN_YEAR = 365
HOURS_IN_DAY = 24
COLLAPSED_NAMES = ("mean", "std", "min", "max")


def representation_column(frame: pd.DataFrame) -> str:
    """集合的表示列。percentile 优先，其次 realization，最后是 member。"""
    for name in ("percentile", "realization", "member"):
        if name in frame.columns:
            return name
    raise ValueError("预报数据需要 member、realization 或 percentile 列")


def check_percentiles(frame: pd.DataFrame) -> None:
    """百分位需要等间距，才能当成等可能样本计算均值和标准差。"""
    values = np.sort(np.unique(frame["percentile"].astype(float)))
    if len(values) < 2:
        return
    spacing = np.diff(values)
    if not np.allclose(spacing, spacing[0]):
        raise ValueError(f"百分位必须等间距，当前为 {values.tolist()}")


def check_transformation(transformation: str | None) -> None:
    if transformation not in (None, "log", "log10", "sqrt", "cbrt"):
        raise ValueError(
            "变换只支持 log、log10、sqrt、cbrt。"
            f"当前传入的是 {transformation}"
        )


def apply_transformation(values, transformation: str | None, pre_transform_addition: float):
    data = np.asarray(values, dtype=np.float64)
    if transformation:
        data = getattr(np, transformation)(data + pre_transform_addition)
    return data


def reverse_transformation(values, transformation: str | None, pre_transform_addition: float):
    data = np.asarray(values, dtype=np.float64)
    if transformation == "log":
        data = np.exp(data) - pre_transform_addition
    elif transformation == "log10":
        data = np.power(10.0, data) - pre_transform_addition
    elif transformation == "sqrt":
        data = np.square(data) - pre_transform_addition
    elif transformation == "cbrt":
        data = np.power(data, 3) - pre_transform_addition
    return data


def _is_collapsed(feature_name: str) -> bool:
    return (
        feature_name in COLLAPSED_NAMES
        or feature_name.startswith("percentile_")
        or feature_name.startswith("members_below")
        or feature_name.startswith("members_above")
    )


def prep_feature(
    frame: pd.DataFrame,
    variable_name: str,
    feature_name: str,
    group_keys: list[str],
    transformation: str | None = None,
    pre_transform_addition: float = 0,
) -> pd.DataFrame:
    """按配置生成一个特征列。"""
    frame = frame.copy()
    if _is_collapsed(feature_name):
        representation = representation_column(frame)
        if representation == "percentile":
            check_percentiles(frame)
        grouped = frame.groupby(group_keys, sort=False)[variable_name]
        if feature_name in COLLAPSED_NAMES:
            feature = getattr(grouped, feature_name)()
            if feature_name == "std":
                feature = feature.fillna(0)
        elif feature_name.startswith("members_below") or feature_name.startswith("members_above"):
            prefix = "members_below_" if feature_name.startswith("members_below") else "members_above_"
            threshold = float(feature_name[len(prefix) :])
            threshold = float(np.asarray(apply_transformation(threshold, transformation, pre_transform_addition)).reshape(-1)[0])
            if prefix.startswith("members_below"):
                flag = frame[variable_name].to_numpy() < threshold
            else:
                flag = frame[variable_name].to_numpy() > threshold
            counted = frame[group_keys].copy()
            counted["_flag"] = flag
            feature = counted.groupby(group_keys, sort=False)["_flag"].sum()
        else:
            percentile = float(feature_name.split("_", 1)[1])
            feature = grouped.quantile(percentile / 100.0)
        feature = feature.rename(f"{variable_name}_{feature_name}").reset_index()
        if feature[f"{variable_name}_{feature_name}"].isnull().all():
            raise ValueError(
                f"变量 {variable_name} 的特征 {feature_name} 全部为缺测"
            )
        frame = frame.merge(feature, on=group_keys, how="left")
        return frame

    if feature_name in {"day_of_year", "day_of_year_sin", "day_of_year_cos"}:
        day = pd.to_datetime(frame["valid_time"]).dt.dayofyear.to_numpy(dtype=np.int32)
        if feature_name == "day_of_year":
            frame[feature_name] = day
        else:
            angle = 2 * np.pi * day / (DAYS_IN_YEAR + 1)
            function = np.sin if feature_name.endswith("sin") else np.cos
            frame[feature_name] = function(angle).astype(np.float32)
        return frame

    if feature_name in {"hour_of_day", "hour_of_day_sin", "hour_of_day_cos"}:
        hour = pd.to_datetime(frame["valid_time"]).dt.hour.to_numpy(dtype=np.int32)
        if feature_name == "hour_of_day":
            frame[feature_name] = hour
        else:
            angle = 2 * np.pi * hour / HOURS_IN_DAY
            function = np.sin if feature_name.endswith("sin") else np.cos
            frame[feature_name] = function(angle).astype(np.float32)
        return frame

    return frame


def prep_features_from_config(
    frame: pd.DataFrame,
    feature_config: dict[str, list[str]],
    group_keys: list[str],
    transformation: str | None = None,
    pre_transform_addition: float = 0,
) -> tuple[pd.DataFrame, list[str]]:
    """按特征配置生成全部特征，并返回模型使用的列名。"""
    feature_columns = []
    for variable_name, feature_names in feature_config.items():
        if variable_name not in frame.columns:
            raise ValueError(f"预报数据中没有特征变量 {variable_name}")
        for feature_name in feature_names:
            frame = prep_feature(
                frame,
                variable_name,
                feature_name,
                group_keys,
                transformation=transformation,
                pre_transform_addition=pre_transform_addition,
            )
            if _is_collapsed(feature_name):
                feature_columns.append(f"{variable_name}_{feature_name}")
            elif feature_name == "static":
                feature_columns.append(variable_name)
            elif feature_name in frame.columns:
                feature_columns.append(feature_name)
            else:
                raise ValueError(f"变量 {variable_name} 不支持特征 {feature_name}")
    return frame, feature_columns


def sanitise_forecast_frame(
    frame: pd.DataFrame,
    feature_config: dict[str, list[str]],
    group_keys: list[str],
) -> pd.DataFrame:
    """每个格点或站点只保留一条记录，并去掉已经折叠过的原始集合列。"""
    representation = representation_column(frame)
    collapsed = []
    for variable_name, feature_names in feature_config.items():
        if any(_is_collapsed(name) for name in feature_names):
            collapsed.append(variable_name)
    subset = (
        frame.sort_values(representation)
        .groupby(group_keys, sort=False, as_index=False)
        .head(1)
        .copy()
    )
    drop_columns = [representation, *collapsed]
    drop_columns = [column for column in drop_columns if column in subset.columns]
    return subset.drop(columns=drop_columns)


def drop_incomplete_rows(
    frame: pd.DataFrame,
    columns: list[str],
    valid_proportion: float = 0.5,
) -> pd.DataFrame:
    """去掉特征或匹配键缺测的行。缺测比例超过阈值时停止训练。"""
    original_length = len(frame)
    if original_length == 0:
        raise ValueError("预报数据为空")
    kept = frame.dropna(subset=columns).copy()
    removed = (original_length - len(kept)) / original_length
    if removed > valid_proportion:
        raise ValueError(
            f"去掉缺测后损失了超过 {valid_proportion * 100:.0f}% 的预报样本，"
            "请检查输入数据和特征配置"
        )
    if kept.empty:
        raise ValueError("去掉缺测后没有剩余预报样本")
    return kept
