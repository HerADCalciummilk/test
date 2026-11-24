# -*- coding: utf-8 -*-
"""评分到融合权重。"""
from __future__ import annotations

import numpy as np


def power_weight(score, power=-2):
    """权重 = 评分 ** power。默认 power=-2。"""
    return np.power(score, power)
