"""CLI for readdata_fromtime_plugin.

Run from this package directory::

    python -m cli.readdata_fromtime_plugin_cli --file-path <template> --file-time 2023070100,2023070101 --glon 70,140,0.05 --glat 0,60,0.05
    python cli/readdata_fromtime_plugin_cli.py --file-path <template> --file-time 2023070100,2023070101 --glon 70,140,0.05 --glat 0,60,0.05
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_args


class ReaddataFromtimePluginCli(CliBase):
    """Concatenate forecast files along time."""

    prog = "python -m cli.readdata_fromtime_plugin_cli"
    description = "Concatenate forecast files along time. Missing args come from resource/conf.ini, then presets."
    epilog = (
        "Example:\n"
        "  python -m cli.readdata_fromtime_plugin_cli "
        "--file-path <template> --file-time 2023070100,2023070101 "
        "--glon 70,140,0.05 --glat 0,60,0.05\n"
        "  python cli/readdata_fromtime_plugin_cli.py "
        "--file-path <template> --file-time 2023070100,2023070101 "
        "--glon 70,140,0.05 --glat 0,60,0.05\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--file-path", default=None, help="Path template. Empty ini value raises.")
        parser.add_argument("--file-time", default=None, help="Comma-separated times. Empty ini value raises.")
        parser.add_argument("--glon", default=None, help="Longitude start,end,step. Empty ini value raises.")
        parser.add_argument("--glat", default=None, help="Latitude start,end,step. Empty ini value raises.")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="Runtime ini. A relative path is resolved from the package root. Omit to use resource/conf.ini.",
        )

    def run(self, config=None, **params) -> int:
        cfg = resolve_args(module="read", config=config, **params)
        shown = {key: value for key, value in cfg.items() if key != "module"}
        print("readdata_fromtime_plugin")
        print(" ".join(f"{key}={value}" for key, value in shown.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return ReaddataFromtimePluginCli().build_parser()


def readdata_fromtime_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。模块方式与直接运行本文件都进这里。"""
    return ReaddataFromtimePluginCli().main(argv)


main = readdata_fromtime_plugin_cli


if __name__ == "__main__":
    raise SystemExit(readdata_fromtime_plugin_cli())
