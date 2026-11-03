"""CLI for simple npy-based STEPS blending verification."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from steps_multi_time_fusion.src.steps_blending_plugin import StepsBlendingPlugin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对两个二维 npy 降水场执行 STEPS 融合。")
    parser.add_argument("--nowcast", required=True, help="nowcast 二维 npy 文件。")
    parser.add_argument("--nwp", required=True, help="NWP 二维 npy 文件。")
    parser.add_argument("--output", required=True, help="融合结果 npy 输出路径。")
    parser.add_argument("--lead-index", type=int, default=1, help="10 分钟步长索引，1 表示 +10min。")
    parser.add_argument("--n-cascade-levels", type=int, default=8)
    parser.add_argument("--tau-min", type=float, default=90.0)
    parser.add_argument("--clim-skill", default=None, help="可选 climatological_skill.npy。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    nowcast = np.load(args.nowcast)
    nwp = np.load(args.nwp)
    plugin = StepsBlendingPlugin(
        n_cascade_levels=args.n_cascade_levels,
        tau_min=args.tau_min,
        use_climatological_skill=bool(args.clim_skill),
        climatological_skill_path=args.clim_skill,
    )
    result = plugin.process(nowcast, nwp, lead_index=args.lead_index)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.save(output, result)
    print(f"融合结果已保存：{output}，形状={result.shape}")


if __name__ == "__main__":
    main()
