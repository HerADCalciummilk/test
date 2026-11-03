# -*- coding: utf-8 -*-
"""
24 小时降水频率匹配订正 CLI：解析参数后调度主程序 ``correct_tp_24h.process``。

项目根目录执行::

    python -m cli --help
    python -m cli --plugin=resource/ecmwf.json
    python -m cli --rpt-list=2025100100,2025100112 --is-multi true --pro-count 8

模块调用::

    from correct_tp_24h import process
    process(plugin="resource/ecmwf.json", is_multi=True, pro_count=8)
"""
import argparse
import sys
from pathlib import Path


def _bootstrap_paths():
    _root = Path(__file__).resolve().parent.parent
    _src = _root / "src"
    # 项目根须在 src 之前，保证 utils 包走根目录 utils/__init__.py（合并 src/utils）
    for p in (str(_root), str(_src)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap_paths()

from correct_tp_24h import process
from utils.util_env import get_resolved_paths


def _parse_bool(s):
    """解析 true/false/1/0；空串视为未指定（None）。"""
    if s is None:
        return None
    t = str(s).strip().lower()
    if t in ("", "none"):
        return None
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔值：true/false/1/0/yes/no")


def _parse_rpt_list(s):
    """逗号分隔起报时间，如 2025100100,2025100112；空串视为未指定。"""
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    items = [x.strip() for x in t.split(",") if x.strip()]
    return items or None


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description=(
            "multi_optimize_tp_24h：24 小时累积降水频率匹配订正。\n"
            "本命令解析参数后调用主程序 correct_tp_24h.process；"
            "未在命令行给出的项从 resource/optimize_tp_24.ini 读取。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli --help\n"
            "  python -m cli\n"
            "      # 使用 ini 中 default_plugin / rpt_list / is_multi / pro_count\n"
            "  python -m cli --plugin=resource/ecmwf.json\n"
            "  python -m cli --rpt-list=2025100100 --is-multi false\n"
            "  python -m cli --rpt-list=2025100100,2025100112 "
            "--is-multi true --pro-count 8\n"
            "\n"
            "说明:\n"
            "  - 起报为空或未指定时，按 ini 的 rpt_list（空则走实时最近一天）\n"
            "  - 预报时效仍由 ini 的 start_dtime/end_dtime/inter_dtime* 决定\n"
            "  - 多进程任务粒度为「起报 × 时效」，与主程序一致\n"
        ),
    )
    parser.add_argument(
        "--plugin",
        default=None,
        metavar="PATH",
        help=(
            "模式路径配置 JSON（含 tp_model / tp_obs / correct_tp_outpath）。"
            "示例：resource/ecmwf.json。"
            "省略则使用 ini 键 default_plugin。"
        ),
    )
    parser.add_argument(
        "--rpt-list",
        dest="rpt_list",
        type=_parse_rpt_list,
        default=None,
        metavar="YYYYMMDDHH[,...]",
        help=(
            "起报时间列表，逗号分隔。"
            "1 个值表示单时次；2 个值表示起止闭区间（按 report_inter 展开）；"
            "省略则使用 ini 键 rpt_list（空表示实时）。"
        ),
    )
    parser.add_argument(
        "--is-multi",
        type=_parse_bool,
        default=None,
        metavar="BOOL",
        help=(
            "是否用多进程并行调度「起报×时效」任务。"
            "取值：true/false（或 1/0）。"
            "省略则使用 ini 键 is_multi（默认 true）。"
        ),
    )
    parser.add_argument(
        "--pro-count",
        type=int,
        default=None,
        metavar="N",
        help=(
            "多进程并行进程数（正整数）。"
            "仅在 is_multi=true 时生效。"
            "省略则使用 ini 键 pro_count（若无则回退旧键 pool_num）。"
        ),
    )
    return parser


def main(argv=None):
    """解析命令行并调度 ``correct_tp_24h.process``。"""
    parser = _build_parser()
    args = parser.parse_args(argv)

    plugin = args.plugin or get_resolved_paths()["default_plugin"]
    process(
        plugin=plugin,
        is_multi=args.is_multi,
        pro_count=args.pro_count,
        rpt_times=args.rpt_list,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
