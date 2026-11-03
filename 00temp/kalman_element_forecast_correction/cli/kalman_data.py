"""Kalman 订正 CLI。

在本包目录执行::

    python -m cli.kalman_data --start-date 20260401 --end-date 20260405
    python cli/kalman_data.py --start-date 20260401 --end-date 20260405
    python -m cli --module kalman --start-date 20260401 --end-date 20260405
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
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

from kalman_element_forecast_correction.src.kalman_cli import run_variable
from kalman_element_forecast_correction.utils.util_env import resolve_kalman
from utils.cli_base import CliBase


def _date_range(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    if start_date:
        start_time = datetime.strptime(start_date, "%Y%m%d")
        end_time = datetime.strptime(end_date or start_date, "%Y%m%d")
        print(f"手动模式：处理 {start_time:%Y%m%d} 至 {end_time:%Y%m%d}")
        return start_time, end_time

    yesterday = datetime.now() - timedelta(days=1)
    start_time = datetime(yesterday.year, yesterday.month, yesterday.day)
    print(f"实时模式：自动处理前一天 {start_time:%Y-%m-%d}")
    return start_time, start_time


class KalmanDataCli(CliBase):
    """运行 SWVL 和 STL 的 Kalman 订正。"""

    prog = "python -m cli.kalman_data"
    description = "运行 SWVL 和 STL 的 Kalman 订正。未给出的项先读 resource/conf.ini 的 [kalman]。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.kalman_data --start-date 20260401 --end-date 20260405\n"
        "  python cli/kalman_data.py --start-date 20260401 --end-date 20260405\n"
        "  python -m cli --module kalman --start-date 20260401 --end-date 20260405\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("start_date", nargs="?", default=None, help="开始日期 YYYYMMDD。省略则读 ini，再没有则用前一天")
        parser.add_argument("end_date", nargs="?", default=None, help="结束日期 YYYYMMDD。省略则读 ini，再没有则等于开始日期")
        parser.add_argument("--base-dir", default=None, help="Kalman 产品根目录。省略则读 ini，预设 /data234/GUO_data/Kalman_data")
        parser.add_argument("--obs-root", default=None, help="CLDAS 实况根目录。省略则读 ini")
        parser.add_argument("--alpha", type=float, default=None, help="误差更新系数。省略则读 ini，预设 0.15")
        parser.add_argument("--back-days", type=int, default=None, help="向前回溯天数。省略则读 ini，预设 5")
        parser.add_argument("--variables", default=None, help="逗号分隔变量。省略则读 ini，预设 SWVL,STL")
        parser.add_argument("--obs-end-time", default=None, help="最新可用观测时间 YYYYMMDDHH。省略则读 ini，空表示不限制")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        start_date=None,
        end_date=None,
        base_dir=None,
        obs_root=None,
        alpha=None,
        back_days=None,
        variables=None,
        obs_end_time=None,
        config=None,
    ) -> int:
        resolved = resolve_kalman(
            start_date=start_date,
            end_date=end_date,
            base_dir=base_dir,
            obs_root=obs_root,
            alpha=alpha,
            back_days=back_days,
            variables=variables,
            obs_end_time=obs_end_time,
            config=config,
        )
        start_time, end_time = _date_range(resolved["start_date"], resolved["end_date"])
        variables_list = [item.strip().upper() for item in resolved["variables"].split(",") if item.strip()]
        obs_end = (
            datetime.strptime(resolved["obs_end_time"], "%Y%m%d%H") if resolved["obs_end_time"] else None
        )
        total_success = 0
        for variable in variables_list:
            total_success += run_variable(
                variable,
                start_time,
                end_time,
                base_dir=resolved["base_dir"],
                obs_root=resolved["obs_root"],
                alpha=resolved["alpha"],
                back_days=resolved["back_days"],
                obs_end_time=obs_end,
            )
        print(f"全部 Kalman 任务完成，成功任务数：{total_success}")
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """解析订正命令。未给出的项由 ``resolve_kalman`` 读 ini / 预设。"""
    return KalmanDataCli().build_parser().parse_args(argv)


def run(args) -> int:
    """按已解析或待补齐的参数执行订正。统一入口传入 Namespace。"""
    return KalmanDataCli().run(
        start_date=getattr(args, "start_date", None),
        end_date=getattr(args, "end_date", None),
        base_dir=getattr(args, "base_dir", None),
        obs_root=getattr(args, "obs_root", None),
        alpha=getattr(args, "alpha", None),
        back_days=getattr(args, "back_days", None),
        variables=getattr(args, "variables", None),
        obs_end_time=getattr(args, "obs_end_time", None),
        config=getattr(args, "config", None),
    )


def kalman_data_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.kalman_data`` 与直接运行本文件都进这里。"""
    return KalmanDataCli().main(argv)


main = kalman_data_cli


if __name__ == "__main__":
    raise SystemExit(kalman_data_cli())
