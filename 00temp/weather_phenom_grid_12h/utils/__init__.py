# -*- coding: utf-8 -*-
"""weather_phenom_grid_12h ``utils`` 包：合并 ``00temp/utils`` 共享插件。

导入约定：``from utils.xxx import ...``（如 ``cli_base``）。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
