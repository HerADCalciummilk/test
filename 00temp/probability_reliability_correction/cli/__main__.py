#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""probability_reliability_correction.cli 包的可执行入口。

包根目录::

    python -m cli
    python -m cli construct
    python -m cli aggregate
    python -m cli manipulate
    python -m cli apply
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

from probability_reliability_correction.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
