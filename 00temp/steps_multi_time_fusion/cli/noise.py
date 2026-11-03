"""CLI for STEPS noise generation.

未在命令行给出的项先读 ``resource/conf.ini`` 的 ``[noise]``，再没有则用预设。

::

    python -m cli.noise --output-dir output_noise --issue-time 202508191600
    python cli/noise.py --output-dir output_noise --issue-time 202508191600
    python -m cli --module noise --output-dir output_noise --issue-time 202508191600
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

from steps_multi_time_fusion.src.noise_plugin import StepsNoisePlugin
from steps_multi_time_fusion.utils.util_env import resolve_noise
from utils.cli_base import CliBase


class NoiseCli(CliBase):
    """生成 STEPS AR(2) 噪声。"""

    prog = "python -m cli.noise"
    description = (
        "生成 STEPS AR(2) 噪声。\n"
        "未给出的项先读 resource/conf.ini 的 [noise]，再没有则用预设。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli.noise --output-dir output_noise --issue-time 202508191600\n"
        "  python cli/noise.py --output-dir output_noise --issue-time 202508191600\n"
        "  python -m cli --module noise "
        "--output-dir output_noise --issue-time 202508191600\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "mode",
            nargs="?",
            choices=["generate"],
            default=None,
            help="当前 CLI 支持 generate。省略则读 ini，预设 generate",
        )
        parser.add_argument(
            "--output-dir",
            default=None,
            help="滤波器和噪声输出目录。省略则读 ini，预设 resource/output/noise",
        )
        parser.add_argument(
            "--issue-time",
            default=None,
            help="起报时间标识，如 202508191600。省略则读 ini 的 issue_time",
        )
        parser.add_argument("--n-levels", type=int, default=None, help="级联层数。省略则读 ini，预设 6")
        parser.add_argument("--phi1", type=float, default=None, help="AR(2) 系数 phi1。省略则读 ini，预设 0.9")
        parser.add_argument("--phi2", type=float, default=None, help="AR(2) 系数 phi2。省略则读 ini，预设 -0.15")
        parser.add_argument(
            "--n-ens-members",
            type=int,
            default=None,
            help="集合成员数。省略则读 ini，预设 5",
        )
        parser.add_argument("--timesteps", type=int, default=None, help="时间步数。省略则读 ini，预设 18")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        mode=None,
        output_dir=None,
        issue_time=None,
        n_levels=None,
        phi1=None,
        phi2=None,
        n_ens_members=None,
        timesteps=None,
        config=None,
    ) -> int:
        resolved = resolve_noise(
            mode=mode,
            output_dir=output_dir,
            issue_time=issue_time,
            n_levels=n_levels,
            phi1=phi1,
            phi2=phi2,
            n_ens_members=n_ens_members,
            timesteps=timesteps,
            config=config,
        )
        plugin = StepsNoisePlugin(
            output_dir=resolved["output_dir"],
            issue_time=resolved["issue_time"],
            n_levels=resolved["n_levels"],
            phi1=resolved["phi1"],
            phi2=resolved["phi2"],
            n_ens_members=resolved["n_ens_members"],
            timesteps=resolved["timesteps"],
        )
        plugin.process(resolved["mode"])
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return NoiseCli().build_parser().parse_args(argv)


def run(args) -> int:
    return NoiseCli().run(
        mode=getattr(args, "mode", None),
        output_dir=getattr(args, "output_dir", None),
        issue_time=getattr(args, "issue_time", None),
        n_levels=getattr(args, "n_levels", None),
        phi1=getattr(args, "phi1", None),
        phi2=getattr(args, "phi2", None),
        n_ens_members=getattr(args, "n_ens_members", None),
        timesteps=getattr(args, "timesteps", None),
        config=getattr(args, "config", None),
    )


def noise_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.noise`` 与直接运行本文件都进这里。"""
    return NoiseCli().main(argv)


main = noise_cli


if __name__ == "__main__":
    raise SystemExit(noise_cli())
