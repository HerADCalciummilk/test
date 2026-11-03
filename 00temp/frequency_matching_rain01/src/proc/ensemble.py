# -*- coding: utf-8 -*-
"""
相似个例评分（``Ensemble``）。

在历史模式场序列中，按多量级 TS 与 BIAS 综合得分，选出与当前场最相似的样本索引。
用于分块订正前的样本筛选；得分越高表示空间降水型越接近。
"""
from __future__ import annotations

import numpy as np

from utils.types import GridData


class Ensemble:
    """历史—当前场相似度计算与排序。"""

    @staticmethod
    def similarity_score_by_ts_and_bias(
        gd_model: GridData,
        gd_fact: GridData,
        rain_limit: float = 0.0,
        smooth_num: int = 0,
        check_limit: float = 0.1,
    ) -> float:
        """
        单量级相似度：TS + 对 BIAS 偏离 1 的惩罚项。

        Parameters
        ----------
        gd_model / gd_fact :
            待比模式场与参照场（此处参照多为当前平滑场）。
        rain_limit :
            小于该值的降水清零后再比。
        smooth_num :
            九点平滑次数。
        check_limit :
            二值化阈值（mm），用于命中/空报/漏报统计。

        Returns
        -------
        float
            综合得分；无有效命中时返回 ``-1.0``。
        """
        model = gd_model.copy_grid_data()
        fact = gd_fact.copy_grid_data()
        model.clear_to_num_less_than(0.0, rain_limit)
        fact.clear_to_num_less_than(0.0, rain_limit)
        model.smooth9(smooth_num)
        fact.smooth9(smooth_num)

        # 二值化后统计列联表：命中 / 漏报 / 空报
        fact_hit = fact.val >= check_limit
        model_hit = model.val >= check_limit
        hit = float(np.count_nonzero(fact_hit & model_hit))
        miss = float(np.count_nonzero(fact_hit & ~model_hit))
        false_alarm = float(np.count_nonzero(~fact_hit & model_hit))

        ts_den = hit + miss + false_alarm
        hm_den = hit + miss
        ts = hit / ts_den if ts_den != 0.0 else 0.0
        bias = (hit + false_alarm) / hm_den if hm_den != 0.0 else 0.0

        # BIAS 越接近 1，附加项越大；全无信号则判为无效相似
        if bias != 0.0 or ts != 0.0:
            return ts + 0.2 / (abs(9.0 * (bias - 1.0)) + 1.0)
        return -1.0

    @staticmethod
    def get_similarity_index_by_ts_and_bias(
        gd_model: list[GridData],
        gd_fact: GridData,
        choose_num: int,
        check_limit: np.ndarray | list[float] | None = None,
        rain_limit: float = 0.0,
        smooth_num: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        对历史样本列表逐个打分，返回得分最高的 ``choose_num`` 个索引及对应得分。

        多量级时对有效得分取平均；某量级得分为负则该量级不参与平均。
        """
        scores = np.zeros(len(gd_model), dtype=float)
        if check_limit is None:
            check_limits = np.array([0.1], dtype=float)
        else:
            check_limits = np.asarray(check_limit, dtype=float)

        for idx, item in enumerate(gd_model):
            valid_scores = []
            for limit in check_limits:
                score = Ensemble.similarity_score_by_ts_and_bias(
                    item, gd_fact, rain_limit, smooth_num, float(limit)
                )
                if score >= 0.0:
                    valid_scores.append(score)
            scores[idx] = float(np.mean(valid_scores)) if valid_scores else 0.0

        # 降序取前 choose_num
        order = np.argsort(scores)[::-1][:choose_num]
        return order.astype(int), scores[order].astype(float)
