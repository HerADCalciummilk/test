"""CLI for STEPS noise generation."""

from __future__ import annotations

import argparse

from steps_multi_time_fusion.src.noise_plugin import StepsNoisePlugin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练 STEPS 非参数滤波器或生成 AR(2) 噪声。")
    parser.add_argument("mode", choices=["generate"], help="当前 CLI 支持 generate；训练建议通过插件传入历史场。")
    parser.add_argument("--output-dir", required=True, help="滤波器和噪声文件输出目录。")
    parser.add_argument("--issue-time", required=True, help="起报时间标识，如 202508191600。")
    parser.add_argument("--n-levels", type=int, default=6)
    parser.add_argument("--phi1", type=float, default=0.9)
    parser.add_argument("--phi2", type=float, default=-0.15)
    parser.add_argument("--n-ens-members", type=int, default=5)
    parser.add_argument("--timesteps", type=int, default=18)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plugin = StepsNoisePlugin(
        output_dir=args.output_dir,
        issue_time=args.issue_time,
        n_levels=args.n_levels,
        phi1=args.phi1,
        phi2=args.phi2,
        n_ens_members=args.n_ens_members,
        timesteps=args.timesteps,
    )
    plugin.process(args.mode)


if __name__ == "__main__":
    main()
