# -*- coding: utf-8 -*-
"""格点→格点融合工具。

查找顺序：本目录 → ``00temp/utils``（cli_base 等）→ ``src/utils``（regrid 内核）。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
