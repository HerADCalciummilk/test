# -*- coding: utf-8 -*-
"""格点→站点插值工具。

查找顺序：本目录 → ``00temp/utils``（``cli_base`` / ``base_plugin`` 等）。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))

__path__ = [_here]
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)
