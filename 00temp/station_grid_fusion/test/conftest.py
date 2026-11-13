# -*- coding: utf-8 -*-
"""把包根与 ``src`` 加入 path，便于测试直接导入插件模块。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
