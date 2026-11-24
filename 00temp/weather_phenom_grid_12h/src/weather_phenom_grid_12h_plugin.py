# -*- coding: utf-8 -*-
"""天气现象综合电码。``process`` 按判识、选取、逻辑、编码顺序调用。"""
from __future__ import annotations

import os
import sys

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)
# 只把包根放进 path。src 目录里也有 utils，插到前面会盖住包级 utils。
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.base_plugin import BasePlugin

from .encoder import DIA_WeatherPhenomEncoder
from .identifier import DIA_WeatherPhenomIdentifier
from .logic_judger import DIA_WeatherPhenomLogicJudger
from .selector import DIA_WeatherPhenomSelector


class WeatherPhenomGrid12hPlugin(BasePlugin):
    """一个 12h 时段的内存判识，不含读文件和写 NC。"""

    def __init__(self):
        self._identifier = DIA_WeatherPhenomIdentifier()
        self._selector = DIA_WeatherPhenomSelector()
        self._judger = DIA_WeatherPhenomLogicJudger()
        self._encoder = DIA_WeatherPhenomEncoder()

    def process(self, data_dict: dict):
        # 判识各天气现象是否出现
        occur = self._identifier.process(data_dict)
        # 选取现象 A、B
        idx_a, idx_b = self._selector.process(occur)
        # 判断转、间、伴有
        logic, idx_final_a, idx_final_b = self._judger.process(idx_a, idx_b, occur)
        # 编成综合电码
        return self._encoder.process(idx_final_a, idx_final_b, logic)
