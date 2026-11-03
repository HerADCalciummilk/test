# -*- coding: utf-8 -*-
"""
逐 3 小时降水频率匹配订正 CLI（``python -m cli`` → ``runner.process``）。

::

    python -m cli --help
    python -m cli ecmwf 2026052208
    python -m cli ecmwf 202605220800
    python -m cli ecmwf 202605220000 202605221200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_ROOT), str(_SRC))):
    sys.path.insert(0, _p)


def _is_datetime_token(token: str) -> bool:
    """与 ``runner._is_datetime_token`` 一致：10 位 ``YYYYMMDDHH`` 或 12 位 ``YYYYMMDDHHMM``。"""
    s = str(token).strip()
    return s.isdigit() and len(s) in (10, 12)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description="逐 3 小时降水频率匹配订正（单模式 QPF 统计订正，时效 3–252h / 步长 3）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli\n"
            "  python -m cli ecmwf 2026052208\n"
            "  python -m cli ecmwf 202605220800\n"
            "  python -m cli ecmwf 202605220000 202605221200\n"
            "  python -m cli --data-key ecmwf --start 2026052208\n\n"
            "模块调用:\n"
            "  from runner import process\n"
            "  process(data_key='ecmwf', run_times=['2026052208'])\n"
        ),
    )
    parser.add_argument(
        "tokens",
        nargs="*",
        metavar="ARG",
        help="兼容旧写法：模式键 + 起报时刻(YYYYMMDDHH 或 YYYYMMDDHHMM)",
    )
    parser.add_argument(
        "--data-key", "--data", "--path",
        dest="data_key", default=None,
        help="模式键，对应 resource/path.json 的 configs",
    )
    parser.add_argument(
        "--start", default=None, metavar="YYYYMMDDHH[MM]",
        help="起报起始时刻（10 或 12 位）；与 --end 组成闭区间（步长 1 小时）",
    )
    parser.add_argument(
        "--end", default=None, metavar="YYYYMMDDHH[MM]",
        help="运行结束时刻（需同时给 --start）",
    )
    return parser


def main(argv=None):
    from runner import process

    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    data_key = args.data_key
    run_times = None
    tokens = list(args.tokens or [])

    pos_key = None
    date_args = []
    for tok in tokens:
        if _is_datetime_token(tok):
            date_args.append(tok)
        elif pos_key is None and not str(tok).startswith("-"):
            pos_key = tok
        else:
            parser.error("无法解析参数: %s" % tok)

    if data_key is None:
        data_key = pos_key

    if args.start:
        date_args = [args.start] + ([args.end] if args.end else [])
    if date_args:
        run_times = date_args

    return process(data_key=data_key, run_times=run_times)


if __name__ == "__main__":
    raise SystemExit(main())
