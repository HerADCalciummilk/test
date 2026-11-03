#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""orographic_enhancement 模块 CLI 入口。"""

from typing import Optional, Sequence


_CLI_SCRIPTS = (
    "orographic_precipitation_downscaling/cli/preprocess_test_data.py",
    "orographic_precipitation_downscaling/cli/dsc_orographic_enhancement.py",
    "orographic_precipitation_downscaling/cli/dsc_orographic_enhancement_uv.py",
    "orographic_precipitation_downscaling/cli/dsc_apply_orographic_enhancement.py",
)


def main(argv: Optional[Sequence[str]] = None):
    """列出可直接运行的 CLI 示例脚本。"""
    lines = [
        "orographic_enhancement 模块 CLI 已改为示例脚本，请直接运行：",
        *(f"  python {script}" for script in _CLI_SCRIPTS),
        "",
        "在脚本底部的 if __name__ == '__main__' 中修改路径与参数后执行。",
    ]
    raise SystemExit("\n".join(lines))
