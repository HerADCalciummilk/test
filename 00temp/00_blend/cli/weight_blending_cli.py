"""CLI for weight_blending.

Run from this package directory::

    python -m cli.weight_blending_cli --weight-power -2
    python cli/weight_blending_cli.py --weight-power -2
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


class WeightBlendingCli(CliBase):
    """基于评分权重的多预报融合。"""

    prog = "python -m cli.weight_blending_cli"
    description = (
        "基于评分权重的多预报融合。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。\n"
        "预报场和评分场是 iris Cube，由 WeightBlending.process 传入。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.weight_blending_cli\n"
        "  python -m cli.weight_blending_cli --weight-power -2\n"
        "  python cli/weight_blending_cli.py --weight-power -2\n"
        "  python -m cli.weight_blending_cli --tolerate-period-mismatch\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--weight-power",
            type=float,
            default=None,
            help="评分换成权重的指数。省略则读 ini，预设 -2，即权重 = 评分 ** -2",
        )
        parser.add_argument(
            "--tolerate-period-mismatch",
            dest="tolerate_period_mismatch",
            action="store_true",
            default=None,
            help="容忍预报时效不一致。省略则读 ini，预设关闭",
        )
        parser.add_argument(
            "--no-tolerate-period-mismatch",
            dest="tolerate_period_mismatch",
            action="store_false",
            default=None,
            help="预报时效必须一致",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        weight_power=None,
        tolerate_period_mismatch=None,
        config=None,
    ) -> int:
        cfg = resolve_args(
            weight_power=weight_power,
            tolerate_period_mismatch=tolerate_period_mismatch,
            config=config,
        )
        print("weight_blending")
        print(
            "weight = score ** {weight_power}; "
            "tolerate_period_mismatch={tolerate_period_mismatch}".format(**cfg)
        )
        print("格点评分会再做 51x51 均值平滑。预报 Cube 请调用 src.weight_blending.WeightBlending.process。")
        return 0


def build_parser() -> argparse.ArgumentParser:
    return WeightBlendingCli().build_parser()


def weight_blending_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.weight_blending_cli`` 与直接运行本文件都进这里。"""
    return WeightBlendingCli().main(argv)


main = weight_blending_cli


if __name__ == "__main__":
    raise SystemExit(weight_blending_cli())
