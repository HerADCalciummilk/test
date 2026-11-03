"""源数据拷贝 CLI。

在本包目录执行::

    python -m cli.trans_data --date 20260401
    python cli/trans_data.py --date 20260401
    python -m cli --module trans --date 20260401
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
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

from kalman_element_forecast_correction.src.data_transfer import (
    DEFAULT_TRANSFER_CONFIG,
    TransferConfig,
    copy_process_data,
)
from kalman_element_forecast_correction.utils.util_env import resolve_trans
from utils.cli_base import CliBase


class TransDataCli(CliBase):
    """复制 SWVL/STL 源 nc 到 Kalman 处理目录。"""

    prog = "python -m cli.trans_data"
    description = "复制 SWVL/STL 源 nc 到 Kalman 处理目录。未给出的项先读 resource/conf.ini 的 [trans]。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.trans_data --date 20260401\n"
        "  python cli/trans_data.py --date 20260401\n"
        "  python -m cli --module trans --date 20260401\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("date", nargs="?", default=None, help="处理日期 YYYYMMDD。省略则读 ini，再没有则用前一天")
        parser.add_argument("--swvl-source", default=None, help="SWVL 源数据根目录。省略则读 ini")
        parser.add_argument("--stl-source", default=None, help="STL 源数据根目录。省略则读 ini")
        parser.add_argument("--target-base", default=None, help="目标 process_data 根目录。省略则读 ini")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        date=None,
        swvl_source=None,
        stl_source=None,
        target_base=None,
        config=None,
    ) -> int:
        resolved = resolve_trans(
            date=date,
            swvl_source=swvl_source,
            stl_source=stl_source,
            target_base=target_base,
            config=config,
        )
        run_date = datetime.strptime(resolved["date"], "%Y%m%d") if resolved["date"] else None
        config_obj = TransferConfig(
            source_bases={"SWVL": resolved["swvl_source"], "STL": resolved["stl_source"]},
            target_base=resolved["target_base"],
            level_mapping=DEFAULT_TRANSFER_CONFIG.level_mapping,
        )
        copy_process_data(run_date, config=config_obj)
        return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """解析拷贝命令。未给出的项由 ``resolve_trans`` 读 ini / 预设。"""
    return TransDataCli().build_parser().parse_args(argv)


def run(args) -> int:
    """按已解析或待补齐的参数复制源数据。统一入口传入 Namespace。"""
    return TransDataCli().run(
        date=getattr(args, "date", None),
        swvl_source=getattr(args, "swvl_source", None),
        stl_source=getattr(args, "stl_source", None),
        target_base=getattr(args, "target_base", None),
        config=getattr(args, "config", None),
    )


def trans_data_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.trans_data`` 与直接运行本文件都进这里。"""
    return TransDataCli().main(argv)


main = trans_data_cli


if __name__ == "__main__":
    raise SystemExit(trans_data_cli())
