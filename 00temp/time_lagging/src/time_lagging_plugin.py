# -*- coding: utf-8 -*-
"""时间滞后集合插件。合并公式在 ``GenerateTimeLaggedEnsemble``。"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent
_ROOT = _SRC.parent
_TEMP = _ROOT.parent
for _path in (str(_TEMP), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from utils.base_plugin import BasePlugin
from time_lagging.src.time_lagging import GenerateTimeLaggedEnsemble


class TimeLaggingPlugin(BasePlugin):
    """把不同起报、同一有效时间的集合成员合并成时间滞后集合。"""

    def process(self, *datasets):
        # 不改公式，只转给原算法
        return GenerateTimeLaggedEnsemble().process(*datasets)
