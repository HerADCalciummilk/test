#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""海陆掩码二值化 CLI。

在本包目录执行::

    python -m cli.anc_generate_landmask_ancillary --landmask-path land.nc --output-path out.nc
    python cli/anc_generate_landmask_ancillary.py --landmask-path land.nc --output-path out.nc

Python::

    from cli.anc_generate_landmask_ancillary import AncGenerateLandmaskAncillaryCli
    AncGenerateLandmaskAncillaryCli.call(landmask_path="land.nc", output_path="out.nc")
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

import meteva_base as meb
import xarray as xr


def _bootstrap_paths() -> None:
    package_root = Path(__file__).resolve().parents[1]
    parent = str(package_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)


_bootstrap_paths()

from utils.cli_base import CliBase


def process(
    landmask_path: str,
    output_path: Optional[str] = None,
    config=None,
) -> xr.DataArray:
    """读取海陆掩码并输出 0/1 二值化结果。

    功能逻辑：
    插值后的海陆掩码场中，格点值为 0~1 之间的浮点数，表示该格点为陆地的概率。
    本方法以 0.5 为阈值进行二值化：
    - 格点值 < 0.5：判定为海，置为 0
    - 格点值 >= 0.5：判定为陆，置为 1
    当output_path不为空时，输出结果为float32类型的二值掩码场。

    输入输出均为 meteva_base 标准六维网格数据（member, level, time, dtime, lat, lon），
    维度保持不变，仅修改格点值。

    参数
    ----------
    landmask_path : str
        输入海陆掩码 nc 文件路径。
    output_path : str, optional
        输出 nc 文件路径。为空时仅返回结果，不写盘。
    config :
        命令行 ``--config`` 传入。本模块无 ini 读取器，不覆盖已给路径。

    返回
    -------
    xr.DataArray
        二值化后的海陆掩码，维度保持输入不变。
    """
    from generate_ancillary.src.generate_ancillary import CorrectLandSeaMask

    landmask = meb.read_griddata_from_nc(landmask_path)
    result = CorrectLandSeaMask().process(landmask)

    if output_path is not None:
        # 避免 meteva_base 在 int32 + scale_factor 编码时触发类型冲突。
        meb.write_griddata_to_nc(result.astype("float32"), output_path, creat_dir=True)
    return result


class AncGenerateLandmaskAncillaryCli(CliBase):
    """以 0.5 为阈值把海陆掩码二值化为 0/1。"""

    prog = "python -m cli.anc_generate_landmask_ancillary"
    description = "读取海陆掩码 nc，以 0.5 为阈值输出 0/1 二值场。"
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli.anc_generate_landmask_ancillary --help\n"
        "  python -m cli.anc_generate_landmask_ancillary "
        "--landmask-path land.nc --output-path out.nc\n"
        "  python cli/anc_generate_landmask_ancillary.py "
        "--landmask-path land.nc --output-path out.nc\n"
        "\n"
        "说明:\n"
        "  - --config 传给 process；本模块无 ini 读取器，省略则不改路径\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--landmask-path",
            dest="landmask_path",
            required=True,
            metavar="PATH",
            help="输入海陆掩码 nc。",
        )
        parser.add_argument(
            "--output-path",
            dest="output_path",
            default=None,
            metavar="PATH",
            help="输出 nc。省略则只返回、不写文件。",
        )
        parser.add_argument(
            "--config",
            dest="config",
            default=None,
            metavar="PATH",
            help=(
                "运行配置文件，传给 process 的 config。"
                "相对路径按项目根解析。"
                "本模块无 ini 读取器，省略则不改路径。"
            ),
        )

    def run(self, landmask_path=None, output_path=None, config=None) -> int:
        process(landmask_path=landmask_path, output_path=output_path, config=config)
        return 0


def anc_generate_landmask_ancillary_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli.anc_generate_landmask_ancillary`` 与直接运行本文件都进这里。"""
    return AncGenerateLandmaskAncillaryCli().main(argv)


main = anc_generate_landmask_ancillary_cli


if __name__ == "__main__":
    raise SystemExit(anc_generate_landmask_ancillary_cli())
