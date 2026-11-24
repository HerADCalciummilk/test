"""分位数回归随机森林工具。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)
