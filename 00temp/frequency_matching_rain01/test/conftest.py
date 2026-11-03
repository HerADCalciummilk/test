# -*- coding: utf-8 -*-
"""项目根优先（加载 ``utils`` 合并 ``src/utils``），再 ``src``（加载 ``proc`` / ``runner``）。"""
import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_test_dir)
_src = os.path.join(_root, "src")
_ordered = (_root, _src)
for _p in _ordered:
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed(_ordered):
    sys.path.insert(0, _p)
