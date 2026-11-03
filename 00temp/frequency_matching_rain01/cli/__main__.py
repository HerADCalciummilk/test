# -*- coding: utf-8 -*-
"""
逐 1 小时降水频率匹配订正 CLI（``python -m cli`` → ``runner.process``）。

项目根目录执行
--------------
::

    python -m cli --help
    python -m cli
    python -m cli ecmwf 202604081130
    python -m cli ecmwf 202604081130 202604081800
    python -m cli --data-key ecmwf --start 202604081130 --end 202604081800
    python -m cli ecmwf 202604081130 202604081800 --is-multi --pro-count 4

模块调用::

    from runner import process
    process(data_key="ecmwf", run_times=["202604081130"], is_multi=True, pro_count=4)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_ROOT), str(_SRC))):
    sys.path.insert(0, _p)


def _is_datetime_token(token: str) -> bool:
    return len(token) == 12 and token.isdigit()


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli",
        description="逐 1 小时降水频率匹配订正（单模式 QPF 统计订正）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli\n"
            "  python -m cli ecmwf 202604081130\n"
            "  python -m cli ecmwf 202604081130 202604081800\n"
            "  python -m cli --data-key ecmwf --start 202604081130\n"
            "  python -m cli ecmwf 202604081130 202604081800 --is-multi --pro-count 4\n\n"
            "模块调用:\n"
            "  from runner import process\n"
            "  process(data_key='ecmwf', run_times=['202604081130'], is_multi=True, pro_count=4)\n"
        ),
    )
    parser.add_argument(
        "tokens",
        nargs="*",
        metavar="ARG",
        help="兼容旧写法：模式键 + 起报时刻(YYYYMMDDHHMM)，如 ecmwf 202604081130 [结束时刻]",
    )
    parser.add_argument(
        "--data-key",
        "--data",
        "--path",
        dest="data_key",
        default=None,
        help="模式键，对应 resource/path.json 的 configs（如 ecmwf）；省略则用 json 的 default",
    )
    parser.add_argument(
        "--start",
        default=None,
        metavar="YYYYMMDDHHMM",
        help="起报/运行起始时刻；与 --end 组成闭区间（步长 1 小时）；省略则用当前时刻",
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="YYYYMMDDHHMM",
        help="运行结束时刻（需同时给 --start）；省略表示仅跑 --start 单时次",
    )
    parser.add_argument(
        "--sample-workers",
        type=int,
        default=None,
        help="历史样本并行读数线程上限（默认读环境变量 QPF_SAMPLE_THREADS 或 4）",
    )
    parser.add_argument(
        "--block-workers",
        type=int,
        default=None,
        help="空间分块订正线程上限（默认读环境变量 QPF_BLOCK_THREADS 或 1）",
    )
    parser.add_argument(
        "--fixed-seed",
        type=int,
        default=None,
        help="固定随机种子（默认读环境变量 QPF_FIXED_RANDOM_SEED）",
    )
    parser.add_argument(
        "--is-multi",
        dest="is_multi",
        action="store_true",
        default=False,
        help="多起报（展开后的 cycles）是否多进程并行（默认关闭，串行）",
    )
    parser.add_argument(
        "--no-is-multi",
        dest="is_multi",
        action="store_false",
        help="多起报时串行执行",
    )
    parser.add_argument(
        "--pro-count",
        type=int,
        default=4,
        help="起报层多进程并行数（--is-multi 时生效），默认 4",
    )
    return parser


def _resolve_cli_args(args: argparse.Namespace) -> tuple[Optional[str], Optional[list[str]]]:
    """合并命名参数与旧式位置参数，得到 (data_key, run_times)。"""
    data_key = args.data_key
    date_tokens: list[str] = []

    for token in args.tokens:
        if token.startswith("--data=") or token.startswith("--path="):
            data_key = token.split("=", 1)[1].strip()
        elif _is_datetime_token(token):
            date_tokens.append(token)
        elif data_key is None:
            data_key = token.strip()
        else:
            raise SystemExit(f"无法识别的参数: {token}")

    if args.start:
        if not _is_datetime_token(args.start):
            raise SystemExit("--start 须为 YYYYMMDDHHMM（12 位数字）")
        date_tokens = [args.start]
        if args.end:
            if not _is_datetime_token(args.end):
                raise SystemExit("--end 须为 YYYYMMDDHHMM（12 位数字）")
            date_tokens.append(args.end)
    elif args.end:
        raise SystemExit("使用 --end 时必须同时指定 --start")

    run_times = date_tokens if date_tokens else None
    return data_key, run_times


def main(argv: Optional[Sequence[str]] = None) -> int:
    """解析命令行并调用 ``runner.process``。"""
    from runner import process

    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    data_key, run_times = _resolve_cli_args(args)
    return process(
        data_key=data_key,
        run_times=run_times,
        sample_workers=args.sample_workers,
        block_workers=args.block_workers,
        fixed_seed=args.fixed_seed,
        is_multi=args.is_multi,
        pro_count=args.pro_count,
    )


if __name__ == "__main__":
    '''
    cd /data/code/nimm_pip_repos/multi_optimize_tp_24h
    python -m cli --help
    python -m cli
    python -m cli --plugin=resource/ecmwf.json
    python -m cli --plugin=resource/CMA_MESO.json
    python -m cli --rpt-list=2025100100 --is-multi false
    python -m cli --rpt-list=2025100100,2025100112 --is-multi true --pro-count 8
    '''
    raise SystemExit(main())
