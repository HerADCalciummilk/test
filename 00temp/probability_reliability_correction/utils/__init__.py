#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""probability_reliability_correction 通用工具。

把 ``00temp/utils`` 并入本包 ``utils``，以便 ``from utils.cli_base import CliBase``。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)

from probability_reliability_correction.utils.base_plugin import BasePlugin, PostProcessingPlugin

__all__ = ["BasePlugin", "PostProcessingPlugin"]
