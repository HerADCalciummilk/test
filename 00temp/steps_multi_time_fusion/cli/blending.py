"""CLI for simple npy-based STEPS blending verification.

未在命令行给出的项先读 ``resource/conf.ini`` 的 ``[blending]``，再没有则用预设。

::

    python -m cli.blending --nowcast nowcast.npy --nwp nwp.npy --output blended.npy
    python cli/blending.py --nowcast nowcast.npy --nwp nwp.npy --output blended.npy
    python -m cli --module blending --nowcast nowcast.npy --nwp nwp.npy --output blended.npy
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    parent = root.parent
    root_s = str(root)
    parent_s = str(parent)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if parent_s not in sys.path:
        sys.path.append(parent_s)


_bootstrap_paths()

import numpy as np

from steps_multi_time_fusion.src.steps_blending_plugin import StepsBlendingPlugin
from steps_multi_time_fusion.utils.util_env import resolve_blending
from utils.cli_base import CliBase


class BlendingCli(CliBase):
    """对两个二维 npy 降水场执行 STEPS 融合。"""

    prog = "python -m cli.blending"
    description = (
        "对两个二维 npy 降水场执行 STEPS 融合。\n"
        "未给出的项先读 resource/conf.ini 的 [blending]，再没有则用预设。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli.blending --nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
        "  python cli/blending.py --nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
        "  python -m cli --module blending "
        "--nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--nowcast", default=None, help="nowcast 二维 npy。省略则读 ini 的 nowcast")
        parser.add_argument("--nwp", default=None, help="NWP 二维 npy。省略则读 ini 的 nwp")
        parser.add_argument(
            "--output",
            default=None,
            help="融合结果 npy。省略则读 ini，预设 resource/output/blended.npy",
        )
        parser.add_argument(
            "--lead-index",
            type=int,
            default=None,
            help="10 分钟步长索引，1 表示 +10min。省略则读 ini，预设 1",
        )
        parser.add_argument(
            "--n-cascade-levels",
            type=int,
            default=None,
            help="级联层数。省略则读 ini，预设 8",
        )
        parser.add_argument(
            "--tau-min",
            type=float,
            default=None,
            help="技能衰减时间尺度（分钟）。省略则读 ini，预设 90",
        )
        parser.add_argument(
            "--clim-skill",
            default=None,
            help="可选 climatological_skill.npy。省略则读 ini，空表示不使用",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        nowcast=None,
        nwp=None,
        output=None,
        lead_index=None,
        n_cascade_levels=None,
        tau_min=None,
        clim_skill=None,
        config=None,
    ) -> int:
        resolved = resolve_blending(
            nowcast=nowcast,
            nwp=nwp,
            output=output,
            lead_index=lead_index,
            n_cascade_levels=n_cascade_levels,
            tau_min=tau_min,
            clim_skill=clim_skill,
            config=config,
        )
        nowcast_arr = np.load(resolved["nowcast"])
        nwp_arr = np.load(resolved["nwp"])
        plugin = StepsBlendingPlugin(
            n_cascade_levels=resolved["n_cascade_levels"],
            tau_min=resolved["tau_min"],
            use_climatological_skill=bool(resolved["clim_skill"]),
            climatological_skill_path=resolved["clim_skill"],
        )
        result = plugin.process(nowcast_arr, nwp_arr, lead_index=resolved["lead_index"])
        output_path = Path(resolved["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, result)
        print(f"融合结果已保存：{output_path}，形状={result.shape}")
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return BlendingCli().build_parser().parse_args(argv)


def run(args) -> int:
    return BlendingCli().run(
        nowcast=getattr(args, "nowcast", None),
        nwp=getattr(args, "nwp", None),
        output=getattr(args, "output", None),
        lead_index=getattr(args, "lead_index", None),
        n_cascade_levels=getattr(args, "n_cascade_levels", None),
        tau_min=getattr(args, "tau_min", None),
        clim_skill=getattr(args, "clim_skill", None),
        config=getattr(args, "config", None),
    )


def blending_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.blending`` 与直接运行本文件都进这里。"""
    return BlendingCli().main(argv)


main = blending_cli


if __name__ == "__main__":
    raise SystemExit(blending_cli())
