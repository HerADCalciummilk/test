#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""比较运算符映射（迁移自 improver.utilities.probability_manipulation）。"""

from __future__ import annotations

import operator
from collections import namedtuple
from typing import Dict


def comparison_operator_dict() -> Dict[str, namedtuple]:
    """字符串比较符 → ``function`` / ``spp_string`` / ``inverse``。"""
    inequality = namedtuple("inequality", "function, spp_string, inverse")

    mapping: Dict[str, namedtuple] = {}
    mapping.update(
        dict.fromkeys(
            ["ge", "GE", ">="],
            inequality(
                function=operator.ge,
                spp_string="greater_than_or_equal_to",
                inverse="lt",
            ),
        )
    )
    mapping.update(
        dict.fromkeys(
            ["gt", "GT", ">"],
            inequality(
                function=operator.gt, spp_string="greater_than", inverse="le"
            ),
        )
    )
    mapping.update(
        dict.fromkeys(
            ["le", "LE", "<="],
            inequality(
                function=operator.le,
                spp_string="less_than_or_equal_to",
                inverse="gt",
            ),
        )
    )
    mapping.update(
        dict.fromkeys(
            ["lt", "LT", "<"],
            inequality(
                function=operator.lt, spp_string="less_than", inverse="ge"
            ),
        )
    )
    return mapping
