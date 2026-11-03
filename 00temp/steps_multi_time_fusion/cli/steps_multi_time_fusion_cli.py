"""统一命令行入口。在本包目录执行 ``python -m cli``。

也可直接运行本文件::

    python cli/steps_multi_time_fusion_cli.py --module noise --issue-time 202508191600
"""
from __future__ import annotations

import argparse
import importlib
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

from steps_multi_time_fusion.utils.util_env import resolve_module
from utils.cli_base import CliBase


def _load_cli(name: str):
    if __package__:
        return importlib.import_module(f".{name}", __package__)
    return importlib.import_module(f"steps_multi_time_fusion.cli.{name}")


class StepsMultiTimeFusionCli(CliBase):
    """STEPS 多时效融合命令行。用 --module 选择噪声、气候态技能或融合。"""

    prog = "python -m cli"
    description = (
        "STEPS 多时效融合命令行。\n"
        "用 --module 选择模块：noise、climatological_skill（或 skill）、blending。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --module noise "
        "--output-dir output_noise --issue-time 202508191600\n"
        "  python cli/noise.py --output-dir output_noise --issue-time 202508191600\n"
        "  python -m cli --module climatological_skill "
        "--input-dir clim_skill_data --output clim_skill.npy\n"
        "  python cli/climatological_skill.py "
        "--input-dir clim_skill_data --output clim_skill.npy\n"
        "  python -m cli --module blending "
        "--nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
        "  python cli/blending.py --nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
        "  python cli/steps_multi_time_fusion_cli.py --module blending "
        "--nowcast nowcast.npy --nwp nwp.npy --output blended.npy\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--module",
            default=None,
            choices=["noise", "skill", "climatological_skill", "blending"],
            help="要运行的模块。省略则读 ini 的 [cli] module",
        )
        parser.add_argument(
            "--mode",
            default=None,
            choices=["generate"],
            help="仅 noise：当前支持 generate。省略则读 ini，预设 generate",
        )
        parser.add_argument(
            "--output-dir",
            default=None,
            help="仅 noise：滤波器和噪声输出目录。省略则读 ini，预设 resource/output/noise",
        )
        parser.add_argument(
            "--issue-time",
            default=None,
            help="仅 noise：起报时间标识，如 202508191600。省略则读 ini",
        )
        parser.add_argument("--n-levels", type=int, default=None, help="仅 noise：级联层数。省略则读 ini，预设 6")
        parser.add_argument("--phi1", type=float, default=None, help="仅 noise：AR(2) 系数 phi1。省略则读 ini，预设 0.9")
        parser.add_argument("--phi2", type=float, default=None, help="仅 noise：AR(2) 系数 phi2。省略则读 ini，预设 -0.15")
        parser.add_argument(
            "--n-ens-members",
            type=int,
            default=None,
            help="仅 noise：集合成员数。省略则读 ini，预设 5",
        )
        parser.add_argument("--timesteps", type=int, default=None, help="仅 noise：时间步数。省略则读 ini，预设 18")
        parser.add_argument(
            "--input-dir",
            default=None,
            help="仅 climatological_skill：daily_skill_*.npy 所在目录。省略则读 ini",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="climatological_skill 或 blending 的输出 npy。省略则读对应节，预设 resource/output 下的文件",
        )
        parser.add_argument("--nowcast", default=None, help="仅 blending：nowcast 二维 npy。省略则读 ini")
        parser.add_argument("--nwp", default=None, help="仅 blending：NWP 二维 npy。省略则读 ini")
        parser.add_argument(
            "--lead-index",
            type=int,
            default=None,
            help="仅 blending：10 分钟步长索引，1 表示 +10min。省略则读 ini，预设 1",
        )
        parser.add_argument(
            "--n-cascade-levels",
            type=int,
            default=None,
            help="仅 blending：级联层数。省略则读 ini，预设 8",
        )
        parser.add_argument(
            "--tau-min",
            type=float,
            default=None,
            help="仅 blending：技能衰减时间尺度（分钟）。省略则读 ini，预设 90",
        )
        parser.add_argument(
            "--clim-skill",
            default=None,
            help="仅 blending：可选 climatological_skill.npy。省略则读 ini，空表示不使用",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, config=None, module=None, **params) -> int:
        name = resolve_module(module, config=config)
        ns = argparse.Namespace(config=config, module=module, **params)
        if name == "noise":
            code = _load_cli("noise").run(ns)
        elif name == "climatological_skill":
            code = _load_cli("climatological_skill").run(ns)
        else:
            code = _load_cli("blending").run(ns)
        return 0 if code is None else int(code)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return StepsMultiTimeFusionCli().build_parser().parse_args(argv)


def steps_multi_time_fusion_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return StepsMultiTimeFusionCli().main(argv)


main = steps_multi_time_fusion_cli


if __name__ == "__main__":
    raise SystemExit(steps_multi_time_fusion_cli())
