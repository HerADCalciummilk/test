#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""站点表校验与对齐工具（模块内部使用）。"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def require_columns(df: pd.DataFrame, columns: Sequence[str]) -> None:
    """检查站点表是否包含所需列；缺少则报错。"""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"站点表缺少列: {missing}；现有列: {list(df.columns)}")


def filter_matching_stations(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    on: str = "id",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按站点编号（默认 ``id``）取出两侧共有的站点记录。"""
    common = pd.Index(left[on]).intersection(pd.Index(right[on]))
    if len(common) == 0:
        raise ValueError(f"两侧在键 {on!r} 上无共同站点")
    return left[left[on].isin(common)].copy(), right[right[on].isin(common)].copy()


def get_neighbour_finding_method_name(land_constraint: bool, similar_altitude: bool) -> str:
    """根据陆地约束与高度接近选项，得到邻点方案名称。"""
    return "nearest{}{}".format(
        "_land" if land_constraint else "",
        "_minimum_dz" if similar_altitude else "",
    )


def align_forecast_truth(
    forecast: pd.DataFrame,
    truth: pd.DataFrame,
    *,
    forecast_col: str,
    truth_col: str,
) -> pd.DataFrame:
    """把预报与实况对齐到相同站点、相同有效时间。

    有效时间 = 起报时间 ``time`` + 时效 ``dtime``（小时）。
    只保留两侧都能对上、且该时刻预报并非全部缺测的记录。
    """
    fc = forecast.copy()
    tr = truth.copy()
    fc["_valid_time"] = pd.to_datetime(fc["time"]) + pd.to_timedelta(
        fc["dtime"].astype(float), unit="h"
    )
    tr["_valid_time"] = pd.to_datetime(tr["time"]) + pd.to_timedelta(
        tr["dtime"].astype(float), unit="h"
    )

    tr_slim = tr[["_valid_time", "id", truth_col]].drop_duplicates(
        subset=["_valid_time", "id"], keep="first"
    )
    tr_slim = tr_slim.rename(columns={truth_col: "_truth_value"})

    fc_for_merge = fc.copy()
    if forecast_col == truth_col:
        fc_for_merge = fc_for_merge.rename(columns={forecast_col: "_forecast_value"})
        fc_value_col = "_forecast_value"
    else:
        fc_value_col = forecast_col

    merged = fc_for_merge.merge(tr_slim, on=["_valid_time", "id"], how="inner")
    if merged.empty:
        raise ValueError(
            "预报与实况在有效时间（time+dtime）与站点 id 上无匹配记录"
        )

    # 某一有效时刻若预报值全部缺测，则该时刻不参与后续拟合
    keep = []
    for vt, grp in merged.groupby("_valid_time", sort=False):
        vals = grp[fc_value_col].to_numpy(dtype=float)
        if not np.isnan(vals).all():
            keep.append(vt)
    merged = merged[merged["_valid_time"].isin(keep)]
    if merged.empty:
        raise ValueError(
            "预报与实况在有效时间（time+dtime）与站点 id 上无匹配记录"
        )

    out = merged.copy()
    if fc_value_col != "_forecast_value":
        out = out.rename(columns={fc_value_col: "_forecast_value"})
    return out
