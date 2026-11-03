# -*- coding: utf-8 -*-
"""
算法核心包（``src/proc``）。

各模块对应订正流水线中的一步，由 ``runner._process_block`` / 格点写出阶段调用：

1. ``Ensemble`` — 历史样本与当前场的 TS+BIAS 相似度排序
2. ``OpticalFlow`` — 由历史模式→实况对估计位移风场
3. ``RainExtrapolation`` — 半拉格朗日平流，将当前降水沿光流位移
4. ``FrequencyMatch`` — 分位数频率匹配，校正降水强度分布
5. ``SpatialAnalysis`` — Cressman 插值与站点约束（格点产品）
"""
from .frequency_match import FrequencyMatch
from .ensemble import Ensemble
from .spatial_analysis import SpatialAnalysis
from .rain_extrapolation import RainExtrapolation
from .optical_flow import OpticalFlow

__all__ = [
    "FrequencyMatch",
    "Ensemble",
    "SpatialAnalysis",
    "RainExtrapolation",
    "OpticalFlow",
]
