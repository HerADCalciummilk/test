"""CLI for extrapolation_plugin.

Run from this package directory::

    python -m cli.extrapolation_plugin_cli --precip obs.nc --velocity uv.nc --timesteps 6
    python cli/extrapolation_plugin_cli.py --precip obs.nc --velocity uv.nc --timesteps 6
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


class ExtrapolationPluginCli(CliBase):
    """半拉格朗日外推。"""

    prog = "python -m cli.extrapolation_plugin_cli"
    description = (
        "半拉格朗日外推。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。\n"
        "只打印解析后的参数，不读取降水场，不运行外推。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.extrapolation_plugin_cli --precip obs.nc --velocity uv.nc --timesteps 6\n"
        "  python cli/extrapolation_plugin_cli.py --precip obs.nc --velocity uv.nc --timesteps 6\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip", default=None, help="降水场路径，多个用逗号分隔。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--velocity", default=None, help="平流速度场路径。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--timesteps", type=int, default=None, help="外推时次数。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--delta-min", dest="delta_min", type=int, default=None, help="实况间隔，分钟。省略则读 ini，预设 10")
        parser.add_argument("--extrap-method", dest="extrap_method", default=None, help="外推方法。省略则读 ini，预设 semilagrangian")
        parser.add_argument("--measure-time", dest="measure_time", action="store_true", default=None, help="统计耗时。省略则读 ini，预设不统计")
        parser.add_argument("--no-measure-time", dest="measure_time", action="store_false", default=None, help="不统计耗时")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        cfg = resolve_args("extrapolation", **params)
        print("extrapolation_plugin")
        print(" ".join(f"{key}={value}" for key, value in cfg.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return ExtrapolationPluginCli().build_parser()


def extrapolation_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.extrapolation_plugin_cli`` 与直接运行本文件都进这里。"""
    return ExtrapolationPluginCli().main(argv)


main = extrapolation_plugin_cli


if __name__ == "__main__":
    raise SystemExit(extrapolation_plugin_cli())
