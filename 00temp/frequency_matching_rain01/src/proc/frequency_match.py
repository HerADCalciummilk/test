# -*- coding: utf-8 -*-
"""
频率匹配订正（``FrequencyMatch``）。

核心思想：用历史样本建立「模式分位 ↔ 实况分位」映射，再把当前模式值
按分段线性变换拉到接近实况气候/样本分布，改善量级系统性偏差。
"""
from __future__ import annotations

import numpy as np

from utils.types import GridData, ScatterData


class FrequencyMatch:
    """CDF 分位数映射与格点场订正。"""

    @staticmethod
    def _randomized_sorted(data: np.ndarray) -> np.ndarray:
        """排序前加微小随机扰动，避免大量相等值导致分位索引退化。"""
        return np.sort(data.astype(float) + np.random.random(data.shape) / 1000.0)

    @staticmethod
    def _flatten_values(data):
        """将格点列表或站点列表展平为一维降水数组。"""
        if len(data) == 0:
            return np.array([], dtype=float)
        if isinstance(data[0], GridData):
            return np.concatenate([item.val.flatten() for item in data])
        return np.array([p.val for item in data for p in item.sta_data], dtype=float)

    @staticmethod
    def get_used_model_level(model_data, fact_data, fact_level, fact_level_limit: int | None = None):
        """
        按实况等级表 ``fact_level`` 反查对应模式分位值，得到映射表两端点列。

        Returns
        -------
        used_model, used_fact :
            等长数组；``used_model[i]`` 映射到 ``used_fact[i]``（mm）。
        """
        model = FrequencyMatch._flatten_values(model_data)
        fact = FrequencyMatch._flatten_values(fact_data)
        if len(model) == 0 or len(fact) == 0:
            return np.array([], dtype=float), np.array([], dtype=float)

        array1 = FrequencyMatch._randomized_sorted(fact)   # 实况经验分布
        array2 = FrequencyMatch._randomized_sorted(model)  # 模式经验分布
        used_model = []
        used_fact = []

        # fact_level_limit：两端各去掉若干样本，抑制极值污染分位
        has_limit = fact_level_limit is not None and fact_level_limit < 0.5 * (len(array1) - 1)
        lower_bound = fact_level_limit if has_limit else 0
        upper_bound = len(array1) - 1 - fact_level_limit if has_limit else len(array1) - 1

        for level in fact_level:
            if has_limit:
                if level >= array1[len(array1) - 1 - fact_level_limit] or level < array1[fact_level_limit]:
                    continue
                search_range = range(lower_bound, upper_bound)
            else:
                if level >= array1[-1] or level < array1[0]:
                    continue
                search_range = range(len(array1) - 1)

            for idx in search_range:
                # 在实况排序序列中定位 level 所在分位区间
                in_range = (
                    array1[idx] < level <= array1[idx + 1]
                    if has_limit
                    else array1[idx] <= level < array1[idx + 1]
                )
                if in_range:
                    # 同一相对分位映射到模式序列，再线性插值
                    idx2 = int((idx + 1) / len(array1) * len(array2)) - 1
                    if 0 <= idx2 < len(array2) - 1:
                        mapped = array2[idx2] + (array2[idx2 + 1] - array2[idx2]) * (
                            level - array1[idx]
                        ) / (array1[idx + 1] - array1[idx])
                        used_model.append(mapped)
                        used_fact.append(level)
                    break
        return np.array(used_model, dtype=float), np.array(used_fact, dtype=float)

    @staticmethod
    def get_used_model_level_and_extend(model_data, fact_data, fact_level, fact_level_limit: int | None = None):
        """
        在 ``get_used_model_level`` 基础上，对超出已建表的最大实况等级做外延：
        下一模式端点取 ``max(末点×2, 目标实况等级)``，避免大雨端无映射。
        """
        used_model, used_fact = FrequencyMatch.get_used_model_level(
            model_data, fact_data, fact_level, fact_level_limit
        )
        if len(used_model) == 0 or len(used_model) >= len(fact_level):
            return used_model, used_fact
        for level in fact_level:
            if level > used_fact[-1]:
                extra_model = max(used_model[-1] * 2.0, level)
                used_model = np.append(used_model, extra_model)
                used_fact = np.append(used_fact, level)
                break
        return used_model, used_fact

    @staticmethod
    def correct_model_data(model_data: GridData, fact_level: np.ndarray, model_level: np.ndarray) -> GridData:
        """
        按映射表 ``(model_level → fact_level)`` 对格点场做分段线性订正。

        - 小于 ``model_level[0]``：按首段比例缩放
        - 中间段：线性插值到对应实况等级
        - 大于末点：按末段比例外延
        """
        output = model_data.copy_grid_data()
        if len(fact_level) == 0:
            return output
        flat = output.val.flatten()
        corrected = flat.copy()
        last = len(fact_level) - 1
        for idx, value in enumerate(flat):
            if value < model_level[0]:
                corrected[idx] = (
                    value * fact_level[0] / model_level[0] if model_level[0] != 0 else 0.0
                )
            elif value < model_level[last]:
                for j in range(last):
                    if model_level[j] <= value < model_level[j + 1]:
                        corrected[idx] = fact_level[j] + (
                            fact_level[j + 1] - fact_level[j]
                        ) * (value - model_level[j]) / (model_level[j + 1] - model_level[j])
                        break
            else:
                corrected[idx] = (
                    value * fact_level[last] / model_level[last]
                    if model_level[last] != 0
                    else 0.0
                )
        output.val = corrected.reshape(output.val.shape)
        return output
