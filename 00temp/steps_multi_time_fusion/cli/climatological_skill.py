"""CLI for climatological skill aggregation from daily skill npy files.

未在命令行给出的项先读 ``resource/conf.ini`` 的 ``[climatological_skill]``，再没有则用预设。

::

    python -m cli.climatological_skill --input-dir clim_skill_data --output clim_skill.npy
    python cli/climatological_skill.py --input-dir clim_skill_data --output clim_skill.npy
    python -m cli --module climatological_skill --input-dir clim_skill_data --output clim_skill.npy
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

from steps_multi_time_fusion.src.climatological_skill import calc_climatological_skill
from steps_multi_time_fusion.utils.util_env import resolve_climatological_skill
from utils.cli_base import CliBase


class ClimatologicalSkillCli(CliBase):
    """根据 daily_skill_*.npy 汇总 climatological skill。"""

    prog = "python -m cli.climatological_skill"
    description = (
        "根据 daily_skill_*.npy 汇总 climatological skill。\n"
        "未给出的项先读 resource/conf.ini 的 [climatological_skill]，再没有则用预设。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli.climatological_skill "
        "--input-dir clim_skill_data --output clim_skill.npy\n"
        "  python cli/climatological_skill.py "
        "--input-dir clim_skill_data --output clim_skill.npy\n"
        "  python -m cli --module climatological_skill "
        "--input-dir clim_skill_data --output clim_skill.npy\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--input-dir",
            default=None,
            help="daily_skill_*.npy 所在目录。省略则读 ini 的 input_dir",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="输出 climatological_skill.npy。省略则读 ini，预设 resource/output/climatological_skill.npy",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, input_dir=None, output=None, config=None) -> int:
        resolved = resolve_climatological_skill(
            input_dir=input_dir,
            output=output,
            config=config,
        )
        directory = Path(resolved["input_dir"])
        daily_files = sorted(directory.glob("daily_skill_*.npy"))
        if not daily_files:
            raise FileNotFoundError(f"未找到 daily_skill_*.npy: {directory}")
        daily_skills = [np.load(path) for path in daily_files]
        clim_skill = calc_climatological_skill(daily_skills)
        output_path = Path(resolved["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(output_path, clim_skill)
        print(f"climatological skill 已保存：{output_path}，形状={clim_skill.shape}")
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return ClimatologicalSkillCli().build_parser().parse_args(argv)


def run(args) -> int:
    return ClimatologicalSkillCli().run(
        input_dir=getattr(args, "input_dir", None),
        output=getattr(args, "output", None),
        config=getattr(args, "config", None),
    )


def climatological_skill_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.climatological_skill`` 与直接运行本文件都进这里。"""
    return ClimatologicalSkillCli().main(argv)


main = climatological_skill_cli


if __name__ == "__main__":
    raise SystemExit(climatological_skill_cli())
