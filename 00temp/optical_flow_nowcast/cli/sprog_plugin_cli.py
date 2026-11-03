"""CLI for sprog_plugin.

Run from this package directory::

    python -m cli.sprog_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
    python cli/sprog_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6
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


class SprogPluginCli(CliBase):
    """S-PROG 临近预报。"""

    prog = "python -m cli.sprog_plugin_cli"
    description = (
        "S-PROG 临近预报。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。\n"
        "只打印解析后的参数，不读取降水场，不运行预报。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.sprog_plugin_cli --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6\n"
        "  python cli/sprog_plugin_cli.py --precip obs1.nc,obs2.nc,obs3.nc --velocity uv.nc --timesteps 6\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip", default=None, help="降水场路径，多个用逗号分隔。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--velocity", default=None, help="平流速度场路径。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--timesteps", type=int, default=None, help="外推时次数。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--delta-min", dest="delta_min", type=int, default=None, help="实况间隔，分钟。省略则读 ini，预设 10")
        parser.add_argument("--precip-thr", dest="precip_thr", type=float, default=None, help="最小可辨降水阈值。省略则读 ini，预设 -5")
        parser.add_argument("--n-cascade-levels", dest="n_cascade_levels", type=int, default=None, help="级联层数。省略则读 ini，预设 6")
        parser.add_argument("--extrap-method", dest="extrap_method", default=None, help="外推方法。省略则读 ini，预设 semilagrangian")
        parser.add_argument("--decomp-method", dest="decomp_method", default=None, help="级联分解。省略则读 ini，预设 fft")
        parser.add_argument("--bandpass-filter-method", dest="bandpass_filter_method", default=None, help="带通滤波。省略则读 ini，预设 gaussian")
        parser.add_argument("--ar-order", dest="ar_order", type=int, default=None, help="自回归阶数。省略则读 ini，预设 2")
        parser.add_argument("--conditional", dest="conditional", action="store_true", default=None, help="只统计超过阈值的格点。省略则读 ini，预设关闭")
        parser.add_argument("--no-conditional", dest="conditional", action="store_false", default=None, help="用全场统计")
        parser.add_argument("--probmatching-method", dest="probmatching_method", default=None, help="概率匹配。省略则读 ini，预设 cdf")
        parser.add_argument("--num-workers", dest="num_workers", type=int, default=None, help="并行 worker 数。省略则读 ini，预设 1")
        parser.add_argument("--fft-method", dest="fft_method", default=None, help="FFT 实现。省略则读 ini，预设 numpy")
        parser.add_argument("--domain", default=None, help="spatial 或 spectral。省略则读 ini，预设 spatial")
        parser.add_argument("--measure-time", dest="measure_time", action="store_true", default=None, help="统计耗时。省略则读 ini，预设不统计")
        parser.add_argument("--no-measure-time", dest="measure_time", action="store_false", default=None, help="不统计耗时")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        cfg = resolve_args("sprog", **params)
        print("sprog_plugin")
        print(" ".join(f"{key}={value}" for key, value in cfg.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return SprogPluginCli().build_parser()


def sprog_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.sprog_plugin_cli`` 与直接运行本文件都进这里。"""
    return SprogPluginCli().main(argv)


main = sprog_plugin_cli


if __name__ == "__main__":
    raise SystemExit(sprog_plugin_cli())
