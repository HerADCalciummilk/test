# -*- coding: utf-8 -*-
"""本算法自用的零散方法，并挂上包内 utils 与 00temp/utils。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_pkg_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "..", "utils"))
for _path in (_pkg_utils, _shared_utils):
    if os.path.isdir(_path) and _path not in __path__:
        __path__.append(_path)
