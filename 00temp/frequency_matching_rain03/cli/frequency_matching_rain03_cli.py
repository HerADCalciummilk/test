# -*- coding: utf-8 -*-
"""逐 3 小时降水频率匹配订正命令行。

在本包目录执行::

    python -m cli ecmwf 2026052208
    python cli/frequency_matching_rain03_cli.py ecmwf 2026052208
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
    """与 ``runner._is_datetime_token`` 一致：10 位 ``YYYYMMDDHH`` 或 12 位 ``YYYYMMDDHHMM``。"""
    s = str(token).strip()
    return s.isdigit() and len(s) in (10, 12)


class FrequencyMatchingRain03Cli(CliBase):
    """``frequency_matching_rain03`` 的命令行。``run`` 转调 ``runner.process``。"""

    description = "逐 3 小时降水频率匹配订正（单模式 QPF 统计订正，时效 3–252h / 步长 3）"
    epilog = (
        "示例:\n"
        "  python -m cli\n"
        "  python -m cli ecmwf 2026052208\n"
        "  python -m cli ecmwf 202605220800\n"
        "  python -m cli ecmwf 202605220000 202605221200\n"
        "  python -m cli --data-key ecmwf --start 2026052208\n\n"
        "模块调用:\n"
        "  from runner import process\n"
        "  process(data_key='ecmwf', run_times=['2026052208'])\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
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
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
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
        config=None,
        log_file=None,
        config_json=None,
        path_json=None,
        station_info=None,
        mask_file=None,
    ) -> int:
        from runner import process

        run_times = None
        tokens = list(tokens or [])

        pos_key = None
        date_args = []
        for tok in tokens:
            if _is_datetime_token(tok):
                date_args.append(tok)
            elif pos_key is None and not str(tok).startswith("-"):
                pos_key = tok
            else:
                self.build_parser().error("无法解析参数: %s" % tok)

        if data_key is None:
            data_key = pos_key

        if start:
            date_args = [start] + ([end] if end else [])
        if date_args:
            run_times = date_args

        return process(
            data_key=data_key,
            run_times=run_times,
            config=config,
            log_file=log_file,
            config_json=config_json,
            path_json=path_json,
            station_info=station_info,
            mask_file=mask_file,
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    return FrequencyMatchingRain03Cli().build_parser()


def frequency_matching_rain03_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return FrequencyMatchingRain03Cli().main(argv)


if __name__ == "__main__":
    raise SystemExit(frequency_matching_rain03_cli())
