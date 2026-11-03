#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""通用工具。

导入约定：``from utils.xxx import ...``。

路径合并顺序：
1. 本目录（算法自带的 ``base_plugin`` 等）
2. 仓库根 ``utils/`` — 共享插件，含 ``pressure_to_height_plugin``
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))

__path__ = [_here]
if os.path.isdir(_shared_utils) and _shared_utils not in __path__:
    __path__.append(_shared_utils)

