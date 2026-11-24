# -*- coding: utf-8 -*-
"""兼容入口：``process`` 转调 ``cli.interp_sg_cressman_cli``。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_paths():
    _src = Path(__file__).resolve().parent
    _root = _src.parent
    _cli = _root / "cli"
    for p in (str(_root), str(_src), str(_cli)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap_paths()

from interp_sg_cressman_cli import process

__all__ = ["process"]
