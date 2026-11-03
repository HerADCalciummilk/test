# -*- coding: utf-8 -*-
"""算法插件：频率匹配、相似、光流、平流、Cressman、日期路径替换。"""
from utils.string_process import StringProcess
from proc.frequency_match import FrequencyMatch
from proc.ensemble import Ensemble
from proc.spatial_analysis import SpatialAnalisis
from proc.optical_flow import OpticalFlow
from proc.rain_extrapolation import RainExtrapolation

__all__ = [
    "StringProcess", "FrequencyMatch", "Ensemble", "SpatialAnalisis",
    "OpticalFlow", "RainExtrapolation",
]
