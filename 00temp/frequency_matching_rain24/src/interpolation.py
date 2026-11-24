# -*- coding: utf-8 -*-
"""度制 GressMan / 插值辅助：直接用 ``interp_sg_cressman.src.gressman_plugin``。"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMP = os.path.normpath(os.path.join(_HERE, "..", ".."))
_CRESS_SRC = os.path.join(_TEMP, "interp_sg_cressman", "src")
_CRESS_ROOT = os.path.join(_TEMP, "interp_sg_cressman")
for _p in (_CRESS_SRC, _CRESS_ROOT):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)

from gressman_plugin import GressManInterpolation, bilinear_interp, mesh_val  # noqa: E402

__all__ = ["GressManInterpolation", "bilinear_interp", "mesh_val"]
