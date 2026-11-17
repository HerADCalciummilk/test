"""在本包目录执行 ``python -m cli``。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = str(_ROOT / "src")
_ROOT_S = str(_ROOT)
for _path in (_SRC, _ROOT_S):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, _SRC)
sys.path.insert(0, _ROOT_S)

from .interpolation_grid_grid_cli import interpolation_grid_grid_cli as main

__all__ = ["main"]
