#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""feels_like_temperature 模块 CLI 入口。

包内 CLI 按子命令分发。路径通过子命令参数传入::

    python -m cli                 # 列出可用子命令
    python -m cli feel-like-temp --temperature-path t.nc --wind-speed-path w.nc --relative-humidity-path rh.nc --pressure-path p.nc --output-path out.nc
    python cli/der_feel_like_temp.py --help
"""

from __future__ import annotations

import importlib
import sys
from typing import Mapping, Optional, Sequence, Tuple

_COMMANDS: Mapping[str, Tuple[str, str]] = {
    "feel-like-temp": (
        "der_feel_like_temp",
        "由气温、风速、湿度、气压计算体感温度",
    ),
}


def _usage() -> str:
    lines = [
        "feels_like_temperature 命令行。请指定子命令，路径通过参数传入。",
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
            "  python -m cli feel-like-temp --temperature-path t.nc "
            "--wind-speed-path w.nc --relative-humidity-path rh.nc "
            "--pressure-path p.nc --output-path out.nc",
            "  python cli/der_feel_like_temp.py --temperature-path t.nc "
            "--wind-speed-path w.nc --relative-humidity-path rh.nc "
            "--pressure-path p.nc --output-path out.nc",
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
