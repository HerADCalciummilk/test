# -*- coding: utf-8 -*-
# pytest 要求本文件名为 conftest.py；实际配置见 test_conftest.py
import os
import sys

_test_dir = os.path.dirname(os.path.abspath(__file__))
if _test_dir not in sys.path:
    sys.path.insert(0, _test_dir)

import test_conftest  # noqa: F401
