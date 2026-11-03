#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""emos_probability_calibration.cli 包的可执行入口。

包根目录::

    python -m cli
    python -m cli emos
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PARENT = _ROOT.parent
for _p in (str(_PARENT), str(_ROOT)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_PARENT), str(_ROOT))):
    sys.path.insert(0, _p)

from emos_probability_calibration.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
