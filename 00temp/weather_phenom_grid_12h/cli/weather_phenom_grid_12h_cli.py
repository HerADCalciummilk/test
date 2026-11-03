# -*- coding: utf-8 -*-
"""网格天气现象综合电码生成命令行。

在本包目录执行::

    python -m cli 2026030100
    python cli/weather_phenom_grid_12h_cli.py 2026030100
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.cli_base import CliBase

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


class WeatherPhenomGrid12hCli(CliBase):
    """``weather_phenom_grid_12h`` 的命令行。``run`` 转调 ``src.main.process``。"""

    description = "网格天气现象综合电码生成 (QX/T 740-2024)"
    epilog = (
        "命令行示例:\n"
        "  python -m cli 2026030100\n"
        "  python -m cli 2026030100 2026030112 --seg-range 1 6\n"
        "  python -m cli 2026030100 2026030112 --is-multi --pro-count 2\n"
        "  python -m cli 2026030100 --output-dir ./PHENOM\n"
        "  python -m cli 2026030100 --stats-only\n\n"
        "模块调用示例:\n"
        "  from src.main import process\n"
        "  process(['2026030100', '2026030112'], is_multi=True, pro_count=2)\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "init_times", nargs="+", metavar="YYYYMMDDHH",
            help="起报时次，可输入多个，如: 2026030100 2026030112",
        )
        parser.add_argument(
            "--output-dir", default=None,
            help="输出目录（默认 ./PHENOM）",
        )
        parser.add_argument(
            "--seg-range", nargs=2, type=int, metavar=("START", "END"),
            default=None,
            help="处理的12h时段范围（包含），如 --seg-range 1 6",
        )
        parser.add_argument(
            "--stats-only", action="store_true",
            help="计算后只打印统计信息，不保存NC文件",
        )
        parser.add_argument(
            "--max-seg-workers", type=int, default=3,
            help="单起报内时段间线程并行数，默认3",
        )
        parser.add_argument(
            "--max-workers", type=int, default=4,
            help="单时段内文件级并行读取线程数，默认4",
        )
        parser.add_argument(
            "--numexpr-threads", type=int, default=None,
            help="设置 NUMEXPR_MAX_THREADS，避免高并发CPU争用",
        )
        parser.add_argument(
            "--data-root", default=None,
            help="数据根目录，覆盖 SCMOC_DATA_ROOT / config.py 默认值",
        )
        parser.add_argument(
            "--is-multi",
            dest="is_multi",
            action="store_true",
            default=False,
            help="多起报时是否多进程执行（默认关闭，串行）",
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
            help="多进程并行数（--is-multi 时生效），默认4",
        )
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        init_times=None,
        output_dir=None,
        seg_range=None,
        stats_only=False,
        max_seg_workers=3,
        max_workers=4,
        numexpr_threads=None,
        data_root=None,
        is_multi=False,
        pro_count=4,
        config=None,
    ) -> int:
        if numexpr_threads is not None:
            os.environ["NUMEXPR_MAX_THREADS"] = str(numexpr_threads)
            os.environ["NUMEXPR_NUM_THREADS"] = str(numexpr_threads)
        if data_root is not None:
            os.environ["SCMOC_DATA_ROOT"] = data_root

        from src.main import process
        from src.processor import DEFAULT_OUTPUT_DIR

        output_dir = output_dir or DEFAULT_OUTPUT_DIR
        seg_range_t = tuple(seg_range) if seg_range else None

        try:
            process(
                init_times=init_times,
                output_dir=output_dir,
                seg_range=seg_range_t,
                max_seg_workers=max_seg_workers,
                max_workers=max_workers,
                data_root=data_root,
                stats_only=stats_only,
                numexpr_threads=numexpr_threads,
                is_multi=is_multi,
                pro_count=pro_count,
                config=config,
            )
        except FileNotFoundError as e:
            print(f"{e}", file=sys.stderr)
            return 1
        except Exception as e:
            logging.error(f"处理异常: {e}", exc_info=True)
            return 2
        return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    return WeatherPhenomGrid12hCli().build_parser()


def weather_phenom_grid_12h_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return WeatherPhenomGrid12hCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(weather_phenom_grid_12h_cli())
