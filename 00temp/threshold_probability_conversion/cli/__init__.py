#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""threshold_probability_conversion 模块 CLI 入口。

包内 CLI 按子命令分发::

    python -m cli                 # 列出可用子命令
    python -m cli threshold
"""

from __future__ import annotations

import importlib
import sys
from typing import Mapping, Optional, Sequence, Tuple

_COMMANDS: Mapping[str, Tuple[str, str]] = {
    "threshold": (
        "prb_threshold",
        "阈值概率转换",
    ),
}


def _usage() -> str:
    lines = [
        "threshold_probability_conversion 含 CLI 示例，请指定子命令：",
        "",
        "用法:",
        "  python -m cli <subcommand>",
        "",
        "子命令:",
    ]
    for name, (mod, desc) in _COMMANDS.items():
        lines.append(f"  {name:<16}  {desc}  (cli/{mod}.py)")
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
