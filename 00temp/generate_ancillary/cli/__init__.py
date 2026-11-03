#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_ancillary 模块 CLI 入口。

包内有多个示例脚本；``python -m cli`` 不默认跑某一个，而是按子命令分发::

    python -m cli                 # 列出可用子命令
    python -m cli landmask
    python -m cli bands
    python -m cli weights
"""

from __future__ import annotations

import importlib
import sys
from typing import Mapping, Optional, Sequence, Tuple

# 子命令 -> (模块名, 说明)
_COMMANDS: Mapping[str, Tuple[str, str]] = {
    "landmask": (
        "anc_generate_landmask_ancillary",
        "海陆掩码二值化",
    ),
    "bands": (
        "dsc_generate_topography_bands_mask",
        "地形带掩码辅助场",
    ),
    "weights": (
        "dsc_generate_topographic_zone_weights",
        "地形带权重辅助场",
    ),
}


def _usage() -> str:
    lines = [
        "generate_ancillary 含多个 CLI 示例，请指定子命令：",
        "",
        "用法:",
        "  python -m cli <subcommand>",
        "",
        "子命令:",
    ]
    for name, (mod, desc) in _COMMANDS.items():
        lines.append(f"  {name:<10}  {desc}  (cli/{mod}.py)")
    lines.extend(
        [
            "",
            "也可直接运行脚本（在脚本 main 中改路径）:",
            *(f"  python cli/{mod}.py" for mod, _ in _COMMANDS.values()),
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """按子命令转发到对应脚本的 ``main``；无参时打印用法。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        raise SystemExit(_usage())

    cmd = args[0]
    if cmd not in _COMMANDS:
        raise SystemExit(f"未知子命令: {cmd}\n\n{_usage()}")

    mod_name, _ = _COMMANDS[cmd]
    module = importlib.import_module(f".{mod_name}", __package__)
    module.main()
