"""CLI corresponding to the original trans_data.sh."""

from __future__ import annotations

import argparse
from datetime import datetime

from kalman_element_forecast_correction.src.data_transfer import DEFAULT_TRANSFER_CONFIG, TransferConfig, copy_process_data


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="复制 SWVL/STL 源 nc 文件到 Kalman 处理目录。")
    parser.add_argument("date", nargs="?", help="处理日期，格式 YYYYMMDD；默认处理前一天。")
    parser.add_argument("--swvl-source", default=DEFAULT_TRANSFER_CONFIG.source_bases["SWVL"], help="SWVL 源数据根目录。")
    parser.add_argument("--stl-source", default=DEFAULT_TRANSFER_CONFIG.source_bases["STL"], help="STL 源数据根目录。")
    parser.add_argument("--target-base", default=DEFAULT_TRANSFER_CONFIG.target_base, help="目标 process_data 根目录。")
    return parser.parse_args()


def main() -> None:
    """Copy process data."""
    args = parse_args()
    run_date = datetime.strptime(args.date, "%Y%m%d") if args.date else None
    config = TransferConfig(
        source_bases={"SWVL": args.swvl_source, "STL": args.stl_source},
        target_base=args.target_base,
        level_mapping=DEFAULT_TRANSFER_CONFIG.level_mapping,
    )
    copy_process_data(run_date, config=config)


if __name__ == "__main__":
    main()
