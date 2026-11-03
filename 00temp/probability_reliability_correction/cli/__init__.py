#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""probability_reliability_correction 模块 CLI 入口。

包内 CLI 按子命令分发::

    python -m cli                 # 列出可用子命令
    python -m cli construct
    python -m cli aggregate
    python -m cli manipulate
    python -m cli apply
"""

from __future__ import annotations

import importlib
import sys
from typing import Mapping, Optional, Sequence, Tuple

_COMMANDS: Mapping[str, Tuple[str, str]] = {
    "construct": (
        "prb_construct_reliability_tables",
        "构建可靠性表",
    ),
    "aggregate": (
        "prb_aggregate_reliability_tables",
        "聚合可靠性表",
    ),
    "manipulate": (
        "prb_manipulate_reliability_table",
        "处理可靠性表",
    ),
    "apply": (
        "prb_apply_reliability_calibration",
        "应用可靠性订正",
    ),
}


def _usage() -> str:
    lines = [
        "probability_reliability_correction 命令行，请指定子命令：",
        "",
        "用法:",
        "  python -m cli <subcommand> [--help] [路径参数...]",
        "",
        "子命令:",
    ]
    for name, (mod, desc) in _COMMANDS.items():
        lines.append(f"  {name:<16}  {desc}  (cli/{mod}.py)")
    lines.extend(
        [
            "",
            "路径在命令行传入。查看全部参数：",
            "  python -m cli construct --help",
            "  python cli/prb_construct_reliability_tables.py --help",
            "",
            "示例:",
            "  python -m cli construct --forecast-path PATH --truth-path PATH [--output-path PATH] [--config PATH]",
            "  python -m cli aggregate --reliability-table-paths PATH [PATH ...] [--output-path PATH]",
            "  python -m cli manipulate --reliability-table-path PATH [--output-path PATH]",
            "  python -m cli apply --forecast-path PATH [--reliability-table-paths PATH ...] [--output-path PATH]",
            "  python cli/prb_apply_reliability_calibration.py --forecast-path PATH --help",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """按子命令把后续参数转给对应入口；无参时打印用法。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(_usage())
        return 0

    cmd = args[0]
    if cmd not in _COMMANDS:
        print(f"未知子命令: {cmd}\n\n{_usage()}", file=sys.stderr)
        return 2

    mod_name, _ = _COMMANDS[cmd]
    module = importlib.import_module(f".{mod_name}", __package__)
    return module.main(args[1:])
