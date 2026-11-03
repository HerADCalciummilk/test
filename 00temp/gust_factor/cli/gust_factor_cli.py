# -*- coding: utf-8 -*-
"""阵风系数命令行。

在本包目录执行::

    python -m cli --mode=calc
    python cli/gust_factor_cli.py --mode=calc
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths():
    _root = Path(__file__).resolve().parent.parent
    _src = _root / "src"
    for p in (str(_root), str(_src)):
        while p in sys.path:
            sys.path.remove(p)
    for p in reversed((str(_root), str(_src))):
        sys.path.insert(0, p)


_bootstrap_paths()

from gust_factor import process
from utils.cli_base import CliBase
from utils.util_env import get_resolved_paths, get_run_params, set_main_ini

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _parse_bool(s):
    if s is None:
        return None
    t = str(s).strip().lower()
    if t in ("", "none"):
        return None
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔值：true/false/1/0")


def _parse_int_list(s):
    if s is None or not str(s).strip():
        return None
    return [int(x.strip()) for x in str(s).split(",") if x.strip()]


class GustFactorCli(CliBase):
    """``gust_factor`` 的命令行。``run`` 转调 ``gust_factor.process``。"""

    description = (
        "gust_factor：历史站点统计阵风系数，并用 U/V 订正阵风预报。\n"
        "未给出的项从 resource/conf.ini 读取。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli\n"
        "  python -m cli --mode=calc --station-dir=resource/test_data\n"
        "  python -m cli --mode=correct --u=a.nc --v=b.nc --factor=c.json\n"
        "  python -m cli --mode=all --fore-hours=24,48,72 --fore-hour=24\n\n"
        "模块: from gust_factor import process\n"
        "  process(mode='all')\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--mode", default=None, choices=["calc", "correct", "all"],
            help="calc=算系数；correct=订正；all=两者（默认读 ini）",
        )
        parser.add_argument(
            "--station-dir", dest="station_csv_dir", default=None, metavar="DIR",
            help="历史站点 CSV 目录",
        )
        parser.add_argument(
            "--fore-hours", type=_parse_int_list, default=None,
            metavar="24,48,72", help="系数统计时效列表",
        )
        parser.add_argument(
            "--factor", dest="factor_path", default=None, metavar="PATH",
            help="阵风系数 JSON 路径",
        )
        parser.add_argument("--u", dest="u_path", default=None, metavar="PATH", help="10m U 格点 NC")
        parser.add_argument("--v", dest="v_path", default=None, metavar="PATH", help="10m V 格点 NC")
        parser.add_argument(
            "--fore-hour", type=int, default=None, metavar="H",
            help="订正所用预报时效",
        )
        parser.add_argument(
            "--output", dest="output_path", default=None, metavar="PATH",
            help="订正阵风 NC 输出路径",
        )
        parser.add_argument(
            "--make-png", dest="make_png", type=_parse_bool, default=None, metavar="BOOL",
            help="是否输出 WS/GUST 对比图",
        )
        parser.add_argument(
            "--show-png", dest="show_png", type=_parse_bool, default=None, metavar="BOOL",
            help="是否弹出对比图窗口",
        )
        parser.add_argument("--ws", dest="ws_path", default=None, metavar="PATH", help="平均风速 NC（出图用）")
        parser.add_argument("--png", dest="png_path", default=None, metavar="PATH", help="对比图输出路径")
        parser.add_argument("--log-file", dest="log_file", default=None, metavar="PATH", help="日志路径模板")
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        mode=None,
        station_csv_dir=None,
        fore_hours=None,
        factor_path=None,
        u_path=None,
        v_path=None,
        fore_hour=None,
        output_path=None,
        make_png=None,
        show_png=None,
        ws_path=None,
        png_path=None,
        log_file=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            get_resolved_paths()
            get_run_params()
            process(
                mode=mode,
                station_csv_dir=station_csv_dir,
                fore_hours=fore_hours,
                factor_path=factor_path,
                u_path=u_path,
                v_path=v_path,
                fore_hour=fore_hour,
                output_path=output_path,
                make_png=make_png,
                show_png=show_png,
                ws_path=ws_path,
                png_path=png_path,
                log_file=log_file,
                config=config,
            )
        finally:
            if config:
                set_main_ini(None)
        return 0


def _build_parser():
    return GustFactorCli().build_parser()


def gust_factor_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return GustFactorCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(gust_factor_cli())
