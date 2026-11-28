# -*- coding: utf-8 -*-
"""网格站点融合工具包。

本目录无业务工具；再挂载同级 ``00temp/utils``（``merge_params`` /
``base_plugin`` 等共享模块），使 ``from utils.xxx`` 在包内可解析。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))

__path__ = [_here]
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)
