"""CLI for climatological skill aggregation from daily skill npy files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from steps_multi_time_fusion.src.climatological_skill import calc_climatological_skill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据 daily_skill_*.npy 汇总 climatological skill。")
    parser.add_argument("--input-dir", required=True, help="daily_skill_*.npy 所在目录。")
    parser.add_argument("--output", required=True, help="输出 climatological_skill.npy 路径。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    daily_files = sorted(input_dir.glob("daily_skill_*.npy"))
    if not daily_files:
        raise FileNotFoundError(f"未找到 daily_skill_*.npy: {input_dir}")
    daily_skills = [np.load(path) for path in daily_files]
    clim_skill = calc_climatological_skill(daily_skills)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, clim_skill)
    print(f"climatological skill 已保存：{output}，形状={clim_skill.shape}")


if __name__ == "__main__":
    main()
