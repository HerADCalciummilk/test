#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""sklearn_code.src 子包。"""
import sys
from pathlib import Path

# 仓库根目录加入 sys.path，支持 notebook 顶层包导入 src.* 的场景。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
