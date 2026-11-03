# -*- coding: utf-8 -*-
import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_test_dir)
_src = os.path.join(_root, "src")
# 项目根须在 src 之前，保证 utils 包走根目录 utils/__init__.py（合并 src/utils）
for p in (_root, _src):
    if p not in sys.path:
        sys.path.insert(0, p)
