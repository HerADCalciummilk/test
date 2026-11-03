"""CLI for lk_plugin.

Run from this package directory::

    python -m cli.lk_plugin_cli --precip obs1.nc,obs2.nc
    python cli/lk_plugin_cli.py --precip obs1.nc,obs2.nc
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


class LkPluginCli(CliBase):
    """Lucas-Kanade 平流估计。"""

    prog = "python -m cli.lk_plugin_cli"
    description = (
        "Lucas-Kanade 平流估计。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。\n"
        "只打印解析后的参数，不读取降水场，不计算平流。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.lk_plugin_cli --precip obs1.nc,obs2.nc\n"
        "  python cli/lk_plugin_cli.py --precip obs1.nc,obs2.nc\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--precip", default=None, help="降水场路径，多个用逗号分隔。留空则读 ini；ini 也为空则报错")
        parser.add_argument("--transform-method", dest="transform_method", default=None, help="db、box、NQ、sqrt。省略则读 ini，预设不变换")
        parser.add_argument("--fd-method", dest="fd_method", default=None, help="特征检测。省略则读 ini，预设 shitomasi")
        parser.add_argument("--interp-method", dest="interp_method", default=None, help="稀疏矢量插值。省略则读 ini，预设 idwinterp2d")
        parser.add_argument("--dense", dest="dense", action="store_true", default=None, help="输出稠密速度场。省略则读 ini，预设开启")
        parser.add_argument("--no-dense", dest="dense", action="store_false", default=None, help="输出稀疏速度矢量")
        parser.add_argument("--nr-std-outlier", dest="nr_std_outlier", type=int, default=None, help="离群剔除的标准差倍数。省略则读 ini，预设 3")
        parser.add_argument("--k-outlier", dest="k_outlier", type=int, default=None, help="局部离群检测的近邻数。省略则读 ini，预设 30")
        parser.add_argument("--size-opening", dest="size_opening", type=int, default=None, help="形态学开运算核大小。省略则读 ini，预设 3")
        parser.add_argument("--decl-scale", dest="decl_scale", type=int, default=None, help="稀疏矢量抽稀尺度（像素）。省略则读 ini，预设 20")
        parser.add_argument("--verbose", dest="verbose", action="store_true", default=None, help="打印过程信息。省略则读 ini，预设不打印")
        parser.add_argument("--no-verbose", dest="verbose", action="store_false", default=None, help="不打印过程信息")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        cfg = resolve_args("lk", **params)
        print("lk_plugin")
        print(" ".join(f"{key}={value}" for key, value in cfg.items()))
        return 0


def build_parser() -> argparse.ArgumentParser:
    return LkPluginCli().build_parser()


def lk_plugin_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.lk_plugin_cli`` 与直接运行本文件都进这里。"""
    return LkPluginCli().main(argv)


main = lk_plugin_cli


if __name__ == "__main__":
    raise SystemExit(lk_plugin_cli())
