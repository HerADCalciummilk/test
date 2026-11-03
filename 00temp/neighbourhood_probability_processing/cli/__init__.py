#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""neighbourhood_probability_processing 模块 CLI 入口。"""

from typing import Optional, Sequence


_CLI_SCRIPTS = (
    "neighbourhood_probability_processing/cli/ens_nbhood.py",
    "neighbourhood_probability_processing/cli/ens_nbhood_iterate_with_mask.py",
    "neighbourhood_probability_processing/cli/ens_nbhood_land_and_sea.py",
    "neighbourhood_probability_processing/cli/preprocess_test_data.py",
)


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "neighbourhood_probability_processing 模块 CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "官方样例预处理（nbhood + use_nbhood，threshold→level）：",
        "  python neighbourhood_probability_processing/cli/preprocess_test_data.py",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
