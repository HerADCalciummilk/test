# -*- coding: utf-8 -*-
"""网格站点融合工具。本地模块优先，并入 ``00temp/utils``。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))

__path__ = [_here]
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)
