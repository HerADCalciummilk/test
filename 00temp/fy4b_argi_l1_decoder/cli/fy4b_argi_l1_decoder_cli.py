# -*- coding: utf-8 -*-
"""FY-4B AGRI L1 解码命令行。

在本包目录执行::

    python -m cli --module batch
    python cli/fy4b_argi_l1_decoder_cli.py --module batch
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    for path in (str(root / "src"), str(root)):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_batch, resolve_module, resolve_single, set_main_ini


def _centers(text: str) -> List[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


class Fy4bArgiL1DecoderCli(CliBase):
    """``fy4b_argi_l1_decoder`` 的命令行。``run`` 先补齐参数，再调用对应插件。"""

    description = (
        "FY-4B AGRI L1 解码。\n"
        "用 --module 选择 batch（按时段扫描）或 single（单文件）。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module batch "
        "--input-root /mnt/data_229/SatelliteData/fy4b_l1 "
        "--output-root /mnt/data_229/SatelliteData/fy4b_channel_latlon "
        "--start-time 2023010406 --end-time 2023010423\n"
        "  python -m cli --module single "
        "--input-hdf D:/testdata/FY4/input.HDF "
        "--output-dir D:/testdata/FY4/channel_data/case_name\n"
        "  python -m cli --module batch\n"
        "  python cli/fy4b_argi_l1_decoder_cli.py --module batch\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置文件，传给入口。相对路径按项目根目录解析。省略则用包内默认 ini。",
        )
        parser.add_argument(
            "--module",
            default=None,
            choices=["batch", "single"],
            help="batch 或 single。省略则读 ini，预设 batch",
        )
        parser.add_argument("--input-root", default=None, help="仅 batch：HDF 根目录。省略则读 ini，空则报错")
        parser.add_argument("--output-root", default=None, help="仅 batch：NetCDF 输出根目录。省略则读 ini，空则报错")
        parser.add_argument(
            "--start-time",
            default=None,
            help="仅 batch：开始时间，YYYYMMDD 或更长。省略则读 ini，空则报错",
        )
        parser.add_argument(
            "--end-time",
            default=None,
            help="仅 batch：结束时间，YYYYMMDD 或更长。省略则读 ini，空则报错",
        )
        parser.add_argument(
            "--centers",
            default=None,
            help="仅 batch：星下点，逗号分隔。省略则读 ini，预设 1050E,1330E",
        )
        parser.add_argument(
            "--overwrite",
            dest="overwrite",
            action="store_true",
            default=None,
            help="仅 batch：覆盖已有 NetCDF。省略则读 ini，预设不覆盖",
        )
        parser.add_argument(
            "--no-overwrite",
            dest="overwrite",
            action="store_false",
            default=None,
            help="仅 batch：已有 NetCDF 则跳过",
        )
        parser.add_argument(
            "--recursive",
            dest="recursive",
            action="store_true",
            default=None,
            help="仅 batch：递归扫描子目录中的 HDF。省略则读 ini，预设不递归",
        )
        parser.add_argument(
            "--no-recursive",
            dest="recursive",
            action="store_false",
            default=None,
            help="仅 batch：只扫描输入目录当前层",
        )
        parser.add_argument("--input-hdf", default=None, help="仅 single：输入 HDF。省略则读 ini，空则报错")
        parser.add_argument("--output-dir", default=None, help="仅 single：通道 NetCDF 输出目录。省略则读 ini，空则报错")
        parser.add_argument("--resolution", type=float, default=None, help="目标分辨率（度）。省略则读 ini，预设 0.04")
        parser.add_argument("--lat-min", type=float, default=None, help="纬度下界。省略则读 ini，预设 -60")
        parser.add_argument("--lat-max", type=float, default=None, help="纬度上界。省略则读 ini，预设 60")
        parser.add_argument(
            "--lon-half-width",
            type=float,
            default=None,
            help="相对中心经度的半宽（度）。省略则读 ini，预设 75",
        )
        parser.add_argument("--channels", default=None, help="通道，如 1-15 或 1,3,7。省略则读 ini，预设 1-15")
        parser.add_argument(
            "--resampling",
            default=None,
            choices=["nearest", "bilinear"],
            help="重采样。省略则读 ini，预设 bilinear",
        )

    def run(
        self,
        module=None,
        input_root=None,
        output_root=None,
        start_time=None,
        end_time=None,
        centers=None,
        overwrite=None,
        recursive=None,
        input_hdf=None,
        output_dir=None,
        resolution=None,
        lat_min=None,
        lat_max=None,
        lon_half_width=None,
        channels=None,
        resampling=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            module_name = resolve_module(module, config=config)
            grid = {
                "resolution": resolution,
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_half_width": lon_half_width,
                "channels": channels,
                "resampling": resampling,
            }
            if module_name == "single":
                cfg = resolve_single(
                    input_hdf=input_hdf,
                    output_dir=output_dir,
                    config=config,
                    **grid,
                )
                from fy4_latlon_channel_plugin import FY4LatLonChannelPlugin

                plugin = FY4LatLonChannelPlugin(
                    resolution=cfg["resolution"],
                    lat_min=cfg["lat_min"],
                    lat_max=cfg["lat_max"],
                    lon_half_width=cfg["lon_half_width"],
                    channels=cfg["channels"],
                    resampling=cfg["resampling"],
                )
                plugin.process(cfg["input_hdf"], cfg["output_dir"])
                return 0

            cfg = resolve_batch(
                input_root=input_root,
                output_root=output_root,
                start_time=start_time,
                end_time=end_time,
                centers=centers,
                overwrite=overwrite,
                recursive=recursive,
                config=config,
                **grid,
            )
            from fy4_batch_latlon_channel_plugin import FY4BatchLatLonChannelPlugin

            plugin = FY4BatchLatLonChannelPlugin(
                input_root=cfg["input_root"],
                output_root=cfg["output_root"],
                start_time=cfg["start_time"],
                end_time=cfg["end_time"],
                resolution=cfg["resolution"],
                lat_min=cfg["lat_min"],
                lat_max=cfg["lat_max"],
                lon_half_width=cfg["lon_half_width"],
                channels=cfg["channels"],
                resampling=cfg["resampling"],
                centers=_centers(cfg["centers"]),
                overwrite=cfg["overwrite"],
                recursive=cfg["recursive"],
            )
            plugin.process()
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return Fy4bArgiL1DecoderCli().build_parser()


def fy4b_argi_l1_decoder_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return Fy4bArgiL1DecoderCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(fy4b_argi_l1_decoder_cli())
