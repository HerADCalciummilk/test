"""CLI corresponding to the original kalman_data.sh."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from kalman_element_forecast_correction.src.kalman_cli import run_variable


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="运行 SWVL 和 STL 的 Kalman 订正流程。")
    parser.add_argument("start_date", nargs="?", help="开始日期，格式 YYYYMMDD；默认处理前一天。")
    parser.add_argument("end_date", nargs="?", help="结束日期，格式 YYYYMMDD；默认等于开始日期。")
    parser.add_argument("--base-dir", default="/data234/GUO_data/Kalman_data", help="Kalman 产品根目录。")
    parser.add_argument("--obs-root", default="/data234/DataPool/01CLDAS/00HRCLDAS/Hourly", help="CLDAS 实况根目录。")
    parser.add_argument("--alpha", type=float, default=0.15, help="Kalman 误差更新系数。")
    parser.add_argument("--back-days", type=int, default=5, help="向前回溯查找或重算误差场的天数。")
    parser.add_argument("--variables", default="SWVL,STL", help="逗号分隔的变量列表，如 SWVL,STL。")
    parser.add_argument("--obs-end-time", help="可选，最新可用观测时间，格式 YYYYMMDDHH；不传则不限制。")
    return parser.parse_args()


def _date_range_from_args(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.start_date:
        start_time = datetime.strptime(args.start_date, "%Y%m%d")
        end_time = datetime.strptime(args.end_date or args.start_date, "%Y%m%d")
        print(f"手动模式：处理 {start_time:%Y%m%d} 至 {end_time:%Y%m%d}")
        return start_time, end_time

    yesterday = datetime.now() - timedelta(days=1)
    start_time = datetime(yesterday.year, yesterday.month, yesterday.day, 0)
    print(f"实时模式：自动处理前一天 {start_time:%Y-%m-%d}")
    return start_time, start_time


def main() -> None:
    """Run configured Kalman variables."""
    args = parse_args()
    start_time, end_time = _date_range_from_args(args)
    variables = [item.strip().upper() for item in args.variables.split(",") if item.strip()]
    obs_end_time = datetime.strptime(args.obs_end_time, "%Y%m%d%H") if args.obs_end_time else None

    total_success = 0
    for variable in variables:
        total_success += run_variable(
            variable,
            start_time,
            end_time,
            base_dir=args.base_dir,
            obs_root=args.obs_root,
            alpha=args.alpha,
            back_days=args.back_days,
            obs_end_time=obs_end_time,
        )

    print(f"全部 Kalman 任务完成，成功任务数：{total_success}")


if __name__ == "__main__":
    main()
