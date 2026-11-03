#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""threshold 通用工具。

把 ``00temp/utils`` 并入本包 ``utils``，以便 ``from utils.cli_base import CliBase``。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)
