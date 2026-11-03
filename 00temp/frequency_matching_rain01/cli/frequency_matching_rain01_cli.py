# -*- coding: utf-8 -*-
"""逐 1 小时降水频率匹配订正命令行。

在本包目录执行::

    python -m cli ecmwf 202604081130
    python cli/frequency_matching_rain01_cli.py ecmwf 202604081130
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

from utils.cli_base import CliBase

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _is_datetime_token(token: str) -> bool:
    return len(token) == 12 and token.isdigit()


class FrequencyMatchingRain01Cli(CliBase):
    """``frequency_matching_rain01`` 的命令行。``run`` 转调 ``runner.process``。"""

    description = "逐 1 小时降水频率匹配订正（单模式 QPF 统计订正）"
    epilog = (
        "示例:\n"
        "  python -m cli\n"
        "  python -m cli ecmwf 202604081130\n"
        "  python -m cli ecmwf 202604081130 202604081800\n"
        "  python -m cli --data-key ecmwf --start 202604081130\n"
        "  python -m cli ecmwf 202604081130 202604081800 --is-multi --pro-count 4\n\n"
        "模块调用:\n"
        "  from runner import process\n"
        "  process(data_key='ecmwf', run_times=['202604081130'], is_multi=True, pro_count=4)\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
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
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=_CONFIG_HELP,
        )
        parser.add_argument(
            "--log-file", dest="log_file", default=None, metavar="PATH",
            help="覆盖 ini 的 log_file（日志模板 log_file_template）。省略则用 ini。",
        )
        parser.add_argument(
            "--config-json", dest="config_json", default=None, metavar="PATH",
            help="覆盖 ini 的 config_json。省略则用 ini。",
        )
        parser.add_argument(
            "--path-json", dest="path_json", default=None, metavar="PATH",
            help="覆盖 ini 的 path_json。省略则用 ini。",
        )
        parser.add_argument(
            "--station-info", dest="station_info", default=None, metavar="PATH",
            help="覆盖 ini 的 station_info。省略则用 ini。",
        )
        parser.add_argument(
            "--mask-file", dest="mask_file", default=None, metavar="PATH",
            help="覆盖 ini 的 mask_file。省略则用 ini。",
        )

    def run(
        self,
        tokens=None,
        data_key=None,
        start=None,
        end=None,
        sample_workers=None,
        block_workers=None,
        fixed_seed=None,
        is_multi=False,
        pro_count=4,
        config=None,
        log_file=None,
        config_json=None,
        path_json=None,
        station_info=None,
        mask_file=None,
    ) -> int:
        from runner import process

        class _Args:
            pass

        args = _Args()
        args.data_key = data_key
        args.tokens = tokens or []
        args.start = start
        args.end = end
        data_key, run_times = _resolve_cli_args(args)
        return process(
            data_key=data_key,
            run_times=run_times,
            sample_workers=sample_workers,
            block_workers=block_workers,
            fixed_seed=fixed_seed,
            is_multi=is_multi,
            pro_count=pro_count,
            config=config,
            log_file=log_file,
            config_json=config_json,
            path_json=path_json,
            station_info=station_info,
            mask_file=mask_file,
        )


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


def _build_arg_parser() -> argparse.ArgumentParser:
    return FrequencyMatchingRain01Cli().build_parser()


def frequency_matching_rain01_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return FrequencyMatchingRain01Cli().main(argv)


if __name__ == "__main__":
    raise SystemExit(frequency_matching_rain01_cli())
