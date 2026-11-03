"""CLI for dB_trans.

Run from this package directory::

    python -m cli.dB_trans_cli --method db --values 0,0.05,0.1,1,10,100
    python cli/dB_trans_cli.py --method db --values 0,0.05,0.1,1,10,100
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def _bootstrap_paths() -> None:
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


_bootstrap_paths()

import numpy as np

from src.dB_trans import NQ_transform, boxcox_transform, dB_transform, sqrt_transform
from utils.cli_base import CliBase
from utils.util_env import METHODS, resolve_args

_TRANSFORMS = {
    "db": dB_transform,
    "box": boxcox_transform,
    "nq": NQ_transform,
    "sqrt": sqrt_transform,
}


def _parse_values(text: str) -> np.ndarray:
    parts = [item.strip() for item in text.split(",") if item.strip()]
    if not parts:
        raise ValueError("values 未包含数值")
    return np.asarray([float(item) for item in parts], dtype=float)


def transform_values(cfg: Dict[str, Any]):
    """按配置变换一维降水强度，返回数组和可打印的元数据。"""
    method = cfg["method"]
    if method == "nq" and cfg["inverse"]:
        raise ValueError("nq 的逆变换依赖正变换留下的 metadata，命令行单次调用只做正变换")
    array = _parse_values(cfg["values"])
    kwargs: Dict[str, Any] = {"inverse": cfg["inverse"]}
    if method in ("db", "box"):
        kwargs["threshold"] = cfg["threshold"]
        if cfg["zerovalue"] is not None:
            kwargs["zerovalue"] = cfg["zerovalue"]
    if method == "box":
        kwargs["Lambda"] = cfg["lambda"]
    if method == "nq":
        kwargs["a"] = cfg["a"]
    result, metadata = _TRANSFORMS[method](array, **kwargs)
    printable = {
        key: value
        for key, value in metadata.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    return result, printable


class DBTransCli(CliBase):
    """降水强度变换。"""

    prog = "python -m cli.dB_trans_cli"
    description = (
        "降水强度变换。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.dB_trans_cli\n"
        "  python -m cli.dB_trans_cli --method db --values 0,0.05,0.1,1,10,100\n"
        "  python cli/dB_trans_cli.py --method db --values 0,0.05,0.1,1,10,100\n"
        "  python -m cli.dB_trans_cli --method box --values 0.1,1,10 --lambda 0\n"
        "  python -m cli.dB_trans_cli --method sqrt --values 0,1,4,9\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--method",
            choices=METHODS,
            default=None,
            help="summary、db、box、nq、sqrt。省略则读 ini，预设 summary",
        )
        parser.add_argument(
            "--values",
            default=None,
            help="逗号分隔的降水强度。除 summary 外必填；省略则读 ini",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=None,
            help="仅 db、box：有雨阈值（毫米/小时）。省略则读 ini，预设 0.1",
        )
        parser.add_argument(
            "--zerovalue",
            type=float,
            default=None,
            help="仅 db、box：无降水格点取值。省略则读 ini，空则由变换函数决定",
        )
        parser.add_argument(
            "--lambda",
            dest="lam",
            type=float,
            default=None,
            help="仅 box：Box-Cox 的 Lambda。省略则读 ini，预设 0",
        )
        parser.add_argument(
            "--a",
            type=float,
            default=None,
            help="仅 nq：绘图位置偏移。省略则读 ini，预设 0",
        )
        parser.add_argument(
            "--inverse",
            dest="inverse",
            action="store_true",
            default=None,
            help="做逆变换。省略则读 ini，预设不做",
        )
        parser.add_argument(
            "--no-inverse",
            dest="inverse",
            action="store_false",
            default=None,
            help="做正变换",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini。相对路径按本包目录解析。省略则使用 resource/conf.ini。",
        )

    def run(
        self,
        method=None,
        values=None,
        threshold=None,
        zerovalue=None,
        lam=None,
        a=None,
        inverse=None,
        config=None,
    ) -> int:
        cfg = resolve_args(
            method=method,
            values=values,
            threshold=threshold,
            zerovalue=zerovalue,
            lam=lam,
            a=a,
            inverse=inverse,
            config=config,
        )
        if cfg["method"] == "summary":
            print("available methods: db, box, nq, sqrt")
            print("未给出的参数来自 resource/conf.ini，缺项再用预设。")
            return 0
        result, metadata = transform_values(cfg)
        print(np.array2string(np.asarray(result), separator=", "))
        print(metadata)
        return 0


def build_parser() -> argparse.ArgumentParser:
    return DBTransCli().build_parser()


def dB_trans_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.dB_trans_cli`` 与直接运行本文件都进这里。"""
    return DBTransCli().main(argv)


main = dB_trans_cli


if __name__ == "__main__":
    raise SystemExit(dB_trans_cli())
