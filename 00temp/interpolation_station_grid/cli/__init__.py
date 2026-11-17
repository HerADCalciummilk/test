"""在本包目录执行 ``python -m cli``。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(_ROOT / "src"), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from .interpolation_station_grid_cli import interpolation_station_grid_cli as main

__all__ = ["main"]
