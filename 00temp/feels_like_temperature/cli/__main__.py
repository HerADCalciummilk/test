#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""feels_like_temperature.cli 包的可执行入口。

包根目录::

    python -m cli
    python -m cli feel-like-temp
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # 本包根目录
_PARENT = _ROOT.parent  # 一般为 00temp，用于 import feels_like_temperature.*
# 父目录优先，保证包名导入稳定
for _p in (str(_PARENT), str(_ROOT)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_PARENT), str(_ROOT))):
    sys.path.insert(0, _p)

from feels_like_temperature.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
