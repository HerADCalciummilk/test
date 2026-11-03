#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""station_height_difference_correction 模块 CLI 入口。"""

from typing import Optional, Sequence


_CLI_SCRIPTS = (
    "station_height_difference_correction/cli/dsc_estimate_dz_rescaling.py",
    "station_height_difference_correction/cli/dsc_apply_dz_rescaling.py",
)


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "station_height_difference_correction 模块 CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
