#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_orographic_smoothing_coefficients 模块 CLI 入口。

包内 CLI 按子命令分发。路径通过子命令参数传入::

    python -m cli                 # 列出可用子命令
    python -m cli smoothing --orography-path orog.nc --output-path out.nc
    python cli/dsc_generate_orographic_smoothing_coefficients.py --help
"""

from __future__ import annotations

import importlib
import sys
from typing import Mapping, Optional, Sequence, Tuple

_COMMANDS: Mapping[str, Tuple[str, str]] = {
    "smoothing": (
        "dsc_generate_orographic_smoothing_coefficients",
        "地形平滑系数",
    ),
}


def _usage() -> str:
    lines = [
        "generate_orographic_smoothing_coefficients 命令行。请指定子命令，路径通过参数传入。",
        "",
        "用法:",
        "  python -m cli <subcommand> [flags]",
        "  python cli/<file>.py [flags]",
        "",
        "子命令:",
    ]
    for name, (mod, desc) in _COMMANDS.items():
        lines.append(f"  {name:<16}  {desc}")
        lines.append(f"      python -m cli {name} --help")
        lines.append(f"      python cli/{mod}.py --help")
    lines.extend(
        [
            "",
            "示例:",
            "  python -m cli smoothing --orography-path orog.nc --output-path out.nc",
            "  python cli/dsc_generate_orographic_smoothing_coefficients.py "
            "--orography-path orog.nc --output-path out.nc",
        ]
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """按子命令转发剩余参数；无参或 --help 时打印用法。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(_usage())
        raise SystemExit(0)

    cmd = args[0]
    if cmd not in _COMMANDS:
        print(f"未知子命令: {cmd}\n\n{_usage()}", file=sys.stderr)
        raise SystemExit(2)

    mod_name, _ = _COMMANDS[cmd]
    module = importlib.import_module(f".{mod_name}", __package__)
    raise SystemExit(module.main(args[1:]))
