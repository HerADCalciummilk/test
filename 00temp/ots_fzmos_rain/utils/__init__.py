# -*- coding: utf-8 -*-
"""OTS 包级 utils。合并共享工具和 ``src/utils`` 里的读写、网格函数。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _path in (_shared_utils, _src_utils):
    if os.path.isdir(_path) and _path not in __path__:
        __path__.append(_path)
