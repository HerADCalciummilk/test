#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""orographic_wind_downscaling 模块 CLI 入口。"""

from typing import Optional, Sequence


_CLI_SCRIPTS = (
    "orographic_wind_downscaling/cli/dsc_wind_downscaling.py",
    "orographic_wind_downscaling/cli/preprocess_test_data.py",
)


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "orographic_wind_downscaling 模块 CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "算法脚本：输入为预处理后的 meb 六维 nc（见 test_data/.../cli_input/）。",
        "预处理（方案一投影 + 方案二经纬）：python orographic_wind_downscaling/cli/preprocess_test_data.py",
        "经纬与投影路径数值对照见 Notebook：orographic_wind_downscaling/nbs/wind_calculations.ipynb",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
