"""CLI for QPF 10-minute split.

在本包目录执行::

    python -m cli.split_qpf [--config PATH] [START_UTC END_UTC]
    python cli/split_qpf.py [--config PATH] [START_UTC END_UTC]

Python::

    from cli.split_qpf import SplitQpfCli
    SplitQpfCli.call(config="resource/split_config.ini")
"""
from __future__ import annotations

import argparse
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

from utils.cli_base import CliBase
from linear_scd_multi_time_fusion.src.conf_overrides import add_conf_arguments


_HISTORY_ERROR = "history range must be omitted or contain exactly START_UTC END_UTC."


class _HistoryRangeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) not in (0, 2):
            parser.error(_HISTORY_ERROR)
        setattr(namespace, self.dest, values)


def _resolve_config(config):
    """相对路径按本包目录解析。省略则交给流程读取默认 ini。"""
    if config is None or str(config).strip() == "":
        return None
    path = Path(config)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


class SplitQpfCli(CliBase):
    """实时拆分 unet_qpf 和 mait_st 为 0.01 度、10 分钟文件。"""

    prog = "python -m cli.split_qpf"
    description = (
        "实时拆分 unet_qpf 和 mait_st 为 0.01 度、10 分钟文件。\n"
        "数据路径从配置文件读取。省略 --config 时使用 resource/split_config.ini。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.split_qpf\n"
        "  python -m cli.split_qpf --config resource/split_config.ini "
        "202608080810 202608080840\n"
        "  python cli/split_qpf.py 202608080810 202608080840\n"
        "  python -m cli.split_qpf --daemon\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "history_range",
            nargs="*",
            action=_HistoryRangeAction,
            help="可选历史范围：START_UTC END_UTC，格式 YYYYMMDDHHMM。",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置文件，传给入口。相对路径按本包目录解析。"
                "省略则使用 resource/split_config.ini。"
            ),
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="按配置中的 [schedule] 持续运行。",
        )
        add_conf_arguments(parser, self.add_optional_bool)

    def run(self, history_range=None, config=None, daemon=False, **conf) -> int:
        history = list(history_range or [])
        if len(history) not in (0, 2):
            print(_HISTORY_ERROR, file=sys.stderr)
            return 2
        from linear_scd_multi_time_fusion.src.split_workflow import process

        process(
            history_range=history,
            config=_resolve_config(config),
            daemon=bool(daemon),
            **conf,
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    return SplitQpfCli().build_parser()


def split_qpf_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.split_qpf`` 与直接运行本文件都进这里。"""
    return SplitQpfCli().main(argv)


main = split_qpf_cli


if __name__ == "__main__":
    raise SystemExit(split_qpf_cli())
