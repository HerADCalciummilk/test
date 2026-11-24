#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""基数据 → 经纬网格附属 CLI（无质控；轻量读入，不依赖 cinrad）。

在本包目录执行::

    python cli/radar_grid_cli.py --input-path PATH --output-dir OUT
    python -m cli.radar_grid_cli --input-path PATH --fields REF,KDP --output-dir OUT

Python::

    from cli.radar_grid_cli import RadarGridCli
    RadarGridCli.call(input_path="PATH", output_dir="OUT")
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    temp_root = root.parent
    temp_s = str(temp_root)
    if temp_s not in sys.path:
        sys.path.insert(0, temp_s)
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.conf_ini import overlay_none


def _parse_fields(fields) -> Tuple[str, ...]:
    if fields is None:
        return ("REF",)
    if isinstance(fields, (list, tuple)):
        parts = [str(p).strip().upper() for p in fields if str(p).strip()]
    else:
        parts = [p.strip().upper() for p in str(fields).split(",") if p.strip()]
    return tuple(parts) or ("REF",)


def _parse_resolution(resolution) -> Tuple[int, int]:
    if resolution is None:
        return (1000, 1000)
    if isinstance(resolution, (list, tuple)) and len(resolution) >= 2:
        return (int(resolution[0]), int(resolution[1]))
    parts = [p.strip() for p in str(resolution).split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError(f"resolution 须为 NX,NY，收到 {resolution!r}")
    return (int(parts[0]), int(parts[1]))


def process(
    input_path: str = None,
    *,
    output_dir: str = None,
    fields: str = None,
    radius: int = 230,
    resolution: Tuple[int, int] = (1000, 1000),
    sweep: int = 0,
    volume: bool = False,
    config: str = None,
) -> Dict[str, Any]:
    """基数据 → 轻量读入 → ``grid_2d`` 经纬网格 → 可选落盘。

    路径类参数默认为 ``None``，可由 ``conf.ini`` ``[radar_grid]`` 填补。
    默认只网格化 ``REF``，写出选定 ``sweep`` 层；``volume=True`` 则写全仰角体。
    """
    _over = overlay_none(
        __file__,
        config,
        {
            "input_path": (input_path, "str"),
            "output_dir": (output_dir, "str"),
            "fields": (fields, "str"),
        },
        section="radar_grid",
    )
    input_path = _over["input_path"]
    output_dir = _over["output_dir"]
    fields = _over["fields"]

    if not input_path:
        raise ValueError(
            "input_path 必填（命令行 --input-path 或 conf.ini [radar_grid]）"
        )

    field_names = _parse_fields(fields)
    res = _parse_resolution(resolution)
    drange = None if radius is None else float(radius)

    from radar_qpe_retrieval.cli.polar_qc import save_meteva_grid_to_netcdf
    from radar_qpe_retrieval.cli.standard_data import load_standard_radar
    from radar_qpe_retrieval.src.polar_grid import gridify_standard_fields

    radar_file = load_standard_radar(str(input_path))
    levels, volumes = gridify_standard_fields(
        radar_file,
        field_names=field_names,
        resolution=res,
        sweep=int(sweep),
        drange=drange,
    )
    if not levels:
        raise ValueError(
            f"未网格化到任何产品：请求 {field_names}，请检查文件可用产品"
        )

    saved: Dict[str, str] = {}
    if output_dir is not None:
        out_root = Path(output_dir)
        out_root.mkdir(parents=True, exist_ok=True)
        to_write = volumes if volume else levels
        for product, grd in to_write.items():
            path = out_root / f"{product}.nc"
            save_meteva_grid_to_netcdf(grd, path)
            saved[product] = str(path)

    return {
        "levels": levels,
        "volumes": volumes,
        "saved": saved,
        "radar_file": radar_file,
        "fields": tuple(levels.keys()),
    }


class RadarGridCli(CliBase):
    """``radar_grid`` 的命令行。``run`` 转调 ``process``。"""

    prog = "python cli/radar_grid_cli.py"
    description = (
        "基数据 → 经纬网格（附属入口；轻量读入，不依赖 cinrad）。\n"
        "省略的可选项保持函数默认值；仍为 None 的路径项可从 "
        "--config / resource/conf.ini 的 [radar_grid] 填补。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python cli/radar_grid_cli.py --help\n"
        "  python cli/radar_grid_cli.py --input-path PATH --output-dir OUT\n"
        "  python -m cli.radar_grid_cli --input-path PATH "
        "--fields REF,KDP --radius 230 --resolution 500,500 --output-dir OUT\n"
        "  python cli/radar_grid_cli.py --input-path PATH --output-dir OUT --volume\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--input-path",
            default=None,
            metavar="PATH",
            help="雷达基数据（标准格式 SDD，可 .bz2/.gz）。必填。",
        )
        parser.add_argument(
            "--output-dir",
            default=None,
            metavar="DIR",
            help="输出目录；写入 {产品}.nc（如 REF.nc）。省略则只计算不落盘。",
        )
        parser.add_argument(
            "--fields",
            default=None,
            metavar="LIST",
            help="逗号分隔产品，如 REF,KDP,ZDR。省略则用 REF。",
        )
        parser.add_argument(
            "--radius",
            type=int,
            default=None,
            help="截断距离 km（drange）。省略则用 230。",
        )
        parser.add_argument(
            "--resolution",
            default=None,
            metavar="NX,NY",
            help="grid_2d 分辨率，如 1000,1000。省略则用 1000,1000。",
        )
        parser.add_argument(
            "--sweep",
            type=int,
            default=None,
            help="输出仰角序号（单层模式）。省略则用 0。",
        )
        self.add_optional_bool(
            parser,
            "--volume",
            help_true="写出全仰角体扫网格。",
            help_false="只写选定 sweep 单层。省略则单层。",
        )
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置 ini（[radar_grid]）。省略则用 resource/conf.ini。",
        )

    def run(self, **params) -> int:
        res = params.get("resolution")
        if isinstance(res, str) and res.strip():
            params["resolution"] = _parse_resolution(res)
        process(**{key: value for key, value in params.items() if value is not None})
        return 0


def radar_grid_cli(argv: Optional[Sequence[str]] = None) -> int:
    return RadarGridCli().main(argv)


def _build_parser():
    return RadarGridCli().build_parser()


main = radar_grid_cli


if __name__ == "__main__":
    raise SystemExit(radar_grid_cli())
