# -*- coding: utf-8 -*-
"""把包根与 ``src`` 加入 path，便于测试直接导入插件模块。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"


def _ensure_paths() -> None:
    root_s, src_s = str(_ROOT), str(_SRC)
    for p in (src_s, root_s):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, src_s)
    sys.path.insert(0, root_s)


_ensure_paths()
