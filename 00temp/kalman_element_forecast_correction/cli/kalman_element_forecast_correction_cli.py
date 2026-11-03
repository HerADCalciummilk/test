"""统一命令行入口。在本包目录执行 ``python -m cli``。

也可直接运行本文件::

    python cli/kalman_element_forecast_correction_cli.py --module kalman
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

from kalman_element_forecast_correction.utils.util_env import resolve_module
from utils.cli_base import CliBase


def _load_cli(name: str):
    if __package__:
        return importlib.import_module(f".{name}", __package__)
    return importlib.import_module(f"kalman_element_forecast_correction.cli.{name}")


class KalmanElementForecastCorrectionCli(CliBase):
    """Kalman 要素预报订正命令行。用 --module 选择订正或拷贝。"""

    prog = "python -m cli"
    description = (
        "Kalman 要素预报订正命令行。\n"
        "用 --module 选择：kalman（订正）、trans（拷贝源数据）。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module kalman\n"
        "  python cli/kalman_element_forecast_correction_cli.py --module kalman\n"
        "  python -m cli --module kalman --start-date 20260401 --end-date 20260405\n"
        "  python cli/kalman_data.py --start-date 20260401 --end-date 20260405\n"
        "  python -m cli --module trans --date 20260401\n"
        "  python cli/trans_data.py --date 20260401\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--module",
            default=None,
            choices=["kalman", "kalman_data", "trans", "trans_data"],
            help="kalman=订正，trans=拷贝源数据。省略则读 ini 的 [cli] module",
        )
        parser.add_argument("--start-date", default=None, help="仅 kalman：开始日期 YYYYMMDD。省略则读 ini，再没有则用前一天")
        parser.add_argument("--end-date", default=None, help="仅 kalman：结束日期 YYYYMMDD。省略则读 ini，再没有则等于开始日期")
        parser.add_argument("--base-dir", default=None, help="仅 kalman：产品根目录。省略则读 ini，预设 /data234/GUO_data/Kalman_data")
        parser.add_argument("--obs-root", default=None, help="仅 kalman：CLDAS 实况根目录。省略则读 ini")
        parser.add_argument("--alpha", type=float, default=None, help="仅 kalman：误差更新系数。省略则读 ini，预设 0.15")
        parser.add_argument("--back-days", type=int, default=None, help="仅 kalman：向前回溯天数。省略则读 ini，预设 5")
        parser.add_argument("--variables", default=None, help="仅 kalman：逗号分隔变量。省略则读 ini，预设 SWVL,STL")
        parser.add_argument("--obs-end-time", default=None, help="仅 kalman：最新观测时间 YYYYMMDDHH。省略则读 ini，空表示不限制")
        parser.add_argument("--date", default=None, help="仅 trans：拷贝日期 YYYYMMDD。省略则读 ini，再没有则用前一天")
        parser.add_argument("--swvl-source", default=None, help="仅 trans：SWVL 源目录。省略则读 ini")
        parser.add_argument("--stl-source", default=None, help="仅 trans：STL 源目录。省略则读 ini")
        parser.add_argument("--target-base", default=None, help="仅 trans：目标 process_data 根目录。省略则读 ini")
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(self, config=None, module=None, **params) -> int:
        name = resolve_module(module, config=config)
        ns = argparse.Namespace(config=config, module=module, **params)
        if name == "trans":
            code = _load_cli("trans_data").run(ns)
        else:
            code = _load_cli("kalman_data").run(ns)
        return 0 if code is None else int(code)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    return KalmanElementForecastCorrectionCli().build_parser().parse_args(argv)


def kalman_element_forecast_correction_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return KalmanElementForecastCorrectionCli().main(argv)


main = kalman_element_forecast_correction_cli


if __name__ == "__main__":
    raise SystemExit(kalman_element_forecast_correction_cli())
