"""Shared utilities for linear_scd_multi_time_fusion.

导入约定：``from utils.xxx import ...``。

路径合并顺序：
1. 本目录
2. ``00temp/utils`` — 共享 ``cli_base`` 等
3. ``src/utils`` — 若存在则并入
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
