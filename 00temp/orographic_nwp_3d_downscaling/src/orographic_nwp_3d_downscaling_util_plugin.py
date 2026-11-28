# -*- coding: utf-8 -*-
"""辅助算法的规范文件名。实现仍在 ``util_plugin.py``。"""
try:
    from .util_plugin import *  # noqa: F401,F403
except ImportError:
    from util_plugin import *  # noqa: F401,F403
