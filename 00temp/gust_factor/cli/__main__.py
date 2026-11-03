# -*- coding: utf-8 -*-
"""
阵风系数 CLI：解析参数后调度 ``gust_factor.process``（无独立 runner）。

项目根目录执行::

    python -m cli --help
    python -m cli
    python -m cli --mode=calc
    python -m cli --mode=correct --fore-hour=24
    python -m cli --mode=all --station-dir=resource/test_data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
from utils.util_env import get_resolved_paths, get_run_params


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


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description=(
            "gust_factor：历史站点统计阵风系数，并用 U/V 订正阵风预报。\n"
            "未给出的项从 resource/gust_factor.ini 读取。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli --help\n"
            "  python -m cli\n"
            "  python -m cli --mode=calc --station-dir=resource/test_data\n"
            "  python -m cli --mode=correct --u=a.nc --v=b.nc --factor=c.json\n"
            "  python -m cli --mode=all --fore-hours=24,48,72 --fore-hour=24\n\n"
            "模块: from gust_factor import process\n"
            "  process(mode='all')\n"
        ),
    )
    parser.add_argument(
        "--mode", default=None, choices=["calc", "correct", "all"],
        help="calc=算系数；correct=订正；all=两者（默认读 ini）",
    )
    parser.add_argument(
        "--station-dir", default=None, metavar="DIR",
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
        "--make-png", type=_parse_bool, default=None, metavar="BOOL",
        help="是否输出 WS/GUST 对比图",
    )
    parser.add_argument("--ws", dest="ws_path", default=None, metavar="PATH", help="平均风速 NC（出图用）")
    parser.add_argument("--png", dest="png_path", default=None, metavar="PATH", help="对比图输出路径")
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    # 尽早触达 ini，缺配置时快速暴露
    get_resolved_paths()
    get_run_params()
    process(
        mode=args.mode,
        station_csv_dir=args.station_dir,
        fore_hours=args.fore_hours,
        factor_path=args.factor_path,
        u_path=args.u_path,
        v_path=args.v_path,
        fore_hour=args.fore_hour,
        output_path=args.output_path,
        make_png=args.make_png,
        ws_path=args.ws_path,
        png_path=args.png_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
