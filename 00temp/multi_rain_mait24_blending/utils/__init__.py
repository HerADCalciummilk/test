# -*- coding: utf-8 -*-
"""MAIT 24h ``utils`` 包：合并 ``00temp/utils`` 共享插件与 ``src/utils`` 算法工具。

导入约定：``from utils.xxx import ...``（如 ``base_plugin``、``util_context``）。
``src/utils/`` 下仅放模块文件，不要添加 ``__init__.py``。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
