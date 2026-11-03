"""CLI for timesplit_hourtomin_plugin.

Run from this package directory::

    python -m cli.timesplit_hourtomin_plugin_cli --ntime 10
    python cli/timesplit_hourtomin_plugin_cli.py --ntime 10
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


class TimesplitHourtominPluginCli(CliBase):
    """Interpolate hourly forecasts to a finer step."""

    prog = "python -m cli.timesplit_hourtomin_plugin_cli"
    description = "Interpolate hourly forecasts to a finer step. Missing args come from resource/conf.ini, then presets."
    epilog = (
        "Example:\n"
        "  python -m cli.timesplit_hourtomin_plugin_cli --ntime 10\n"
        "  python cli/timesplit_hourtomin_plugin_cli.py --ntime 10\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--ntime", type=int, default=None, help="Output step. Preset 10.")
        parser.add_argument("--is-min", dest="is_min", action="store_true", default=None, help="Use minutes. Preset on.")
        parser.add_argument("--no-is-min", dest="is_min", action="store_false", default=None, help="Use hours.")
        parser.add_argument("--index", default=None, choices=["dtime", "time"], help="Axis to interpolate. Preset dtime.")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="Runtime ini. A relative path is resolved from the package root. Omit to use resource/conf.ini.",
        )

    def run(self, config=None, **params) -> int:
        cfg = resolve_args(module="hourtomin", config=config, **params)
        shown = {key: value for key, value in cfg.items() if key != "module"}
        print("timesplit_hourtomin_plugin")
        print(" ".join(f"{key}={value}" for key, value in shown.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return TimesplitHourtominPluginCli().build_parser()


def timesplit_hourtomin_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。模块方式与直接运行本文件都进这里。"""
    return TimesplitHourtominPluginCli().main(argv)


main = timesplit_hourtomin_plugin_cli


if __name__ == "__main__":
    raise SystemExit(timesplit_hourtomin_plugin_cli())
