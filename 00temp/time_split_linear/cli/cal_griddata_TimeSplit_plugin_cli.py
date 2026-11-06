"""CLI for cal_griddata_TimeSplit_plugin.

Run from this package directory::

    python -m cli.cal_griddata_TimeSplit_plugin_cli --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100
    python cli/cal_griddata_TimeSplit_plugin_cli.py --input-fh 0,72,3 --output-fh 0,72,1 --input-fmt <template> --time 2023070100
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


class CalGriddataTimeSplitPluginCli(CliBase):
    """Split coarse forecast lead times."""

    prog = "python -m cli.cal_griddata_TimeSplit_plugin_cli"
    description = "Split coarse forecast lead times. Missing args come from resource/conf.ini, then presets."
    epilog = (
        "Example:\n"
        "  python -m cli.cal_griddata_TimeSplit_plugin_cli "
        "--input-fh 0,72,3 --output-fh 0,72,1 "
        "--input-fmt <template> --time 2023070100\n"
        "  python cli/cal_griddata_TimeSplit_plugin_cli.py "
        "--input-fh 0,72,3 --output-fh 0,72,1 "
        "--input-fmt <template> --time 2023070100\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--input-fh", default=None, help="Input leads start,stop,step. Empty ini value raises.")
        parser.add_argument("--output-fh", default=None, help="Output leads start,stop,step. Empty ini value raises.")
        parser.add_argument("--interp-method", default=None, help="Interpolation. Preset slinear.")
        parser.add_argument("--input-fmt", default=None, help="Input path template. Empty ini value raises.")
        parser.add_argument("--time", default=None, help="Issue time. Empty ini value raises.")
        parser.add_argument("--output-fmt", default=None, help="Output path template. Empty means do not write.")
        parser.add_argument("--uv-fmt", default=None, help="V-wind path template. Empty means skip wind speed.")
        parser.add_argument("--delta-hour", default=None, help="Delta lead. Empty means skip the difference.")
        parser.add_argument("--is-fill0", dest="is_fill0", action="store_true", default=None, help="Fill missing values with 0.")
        parser.add_argument("--no-is-fill0", dest="is_fill0", action="store_false", default=None, help="Do not fill missing values with 0.")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="Runtime ini. A relative path is resolved from the package root. Omit to use resource/conf.ini.",
        )

    def run(self, config=None, **params) -> int:
        cfg = resolve_args(module="timesplit", config=config, **params)
        shown = {key: value for key, value in cfg.items() if key != "module"}
        print("cal_griddata_TimeSplit_plugin")
        print(" ".join(f"{key}={value}" for key, value in shown.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return CalGriddataTimeSplitPluginCli().build_parser()


def cal_griddata_TimeSplit_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。模块方式与直接运行本文件都进这里。"""
    return CalGriddataTimeSplitPluginCli().main(argv)


main = cal_griddata_TimeSplit_plugin_cli


if __name__ == "__main__":
    raise SystemExit(cal_griddata_TimeSplit_plugin_cli())
