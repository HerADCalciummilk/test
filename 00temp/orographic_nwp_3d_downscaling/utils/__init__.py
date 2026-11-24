# -*- coding: utf-8 -*-
"""快速精细化插值工具。本地模块优先，并入 ``00temp/utils``。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
