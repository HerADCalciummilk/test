#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""feels_like_temperature 通用工具。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)

