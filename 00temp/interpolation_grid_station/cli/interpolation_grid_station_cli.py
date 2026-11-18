# -*- coding: utf-8 -*-
"""格点→站点插值命令行。

在本包目录执行::

    python -m cli --module linear --grid a.nc --sta sta.csv
    python cli/interpolation_grid_station_cli.py --module nearest --grid a.nc --sta sta.csv --output out.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    src = str(root / "src")
    root_s = str(root)
    for path in (src, root_s):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, src)
    sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_args, resolve_module, set_main_ini


class InterpolationGridStationCli(CliBase):
    """``interpolation_grid_station`` 的命令行。``run`` 先补齐参数，再调用对应插件。"""

    description = (
        "格点→站点插值。\n"
        "用 --module 选择 linear、nearest、cubic。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module linear "
        "--grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv\n"
        "  python -m cli --module nearest "
        "--grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv "
        "--output out.csv\n"
        "  python -m cli --module cubic "
        "--grid resource/2026100900.024.nc --sta resource/2026100900.024_sta.csv "
        "--output out.m3\n"
        "  python -m cli --module linear --used-coords xydt "
        "--grid multi_dtime.nc --sta sta.csv\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置文件。相对路径按项目根目录解析。省略则用包内默认 ini。",
        )
        parser.add_argument(
            "--module",
            default=None,
            choices=["linear", "nearest", "cubic"],
            help="linear / nearest / cubic。省略则读 ini，预设 linear",
        )
        parser.add_argument("--grid", default=None, help="源格点 nc/m4。省略则读 ini，空则报错")
        parser.add_argument("--sta", default=None, help="目标站点 csv/m3。省略则读 ini，空则报错")
        parser.add_argument(
            "--grid-type",
            default=None,
            metavar="nc|m4",
            help="源格点格式。省略则读 ini；再无则按扩展名（.nc→nc，否则 m4）",
        )
        parser.add_argument(
            "--sta-type",
            default=None,
            metavar="csv|m3",
            help="站点格式。省略则读 ini；再无则按扩展名（.csv→csv，否则 m3）",
        )
        parser.add_argument("--output", default=None, help="可选输出站点路径（csv/m3）")
        parser.add_argument(
            "--output-type",
            default=None,
            metavar="csv|m3",
            help="输出格式。省略则读 ini；再无则按 output 扩展名",
        )
        parser.add_argument(
            "--used-coords",
            default=None,
            help='插值坐标，仅 linear：xy/xyz/xydt。省略则读 ini，预设 xy',
        )

    def run(
        self,
        module=None,
        grid=None,
        sta=None,
        grid_type=None,
        sta_type=None,
        output=None,
        output_type=None,
        used_coords=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            module_name = resolve_module(module, config=config)
            cfg = resolve_args(
                module=module_name,
                grid=grid,
                sta=sta,
                output=output,
                used_coords=used_coords,
                grid_type=grid_type,
                sta_type=sta_type,
                output_type=output_type,
                config=config,
            )
            import meteva_base as meb

            if cfg["grid_type"] == "nc":
                grd_in = meb.read_griddata_from_nc(cfg["grid"])
            else:
                grd_in = meb.read_griddata_from_micaps4(cfg["grid"])
            if cfg["sta_type"] == "csv":
                sta_in = meb.read_stadata_from_csv(cfg["sta"])
            else:
                sta_in = meb.read_stadata_from_micaps3(cfg["sta"])

            if module_name == "linear":
                from interp_gs_linear_plugin import InterpGsLinear

                result = InterpGsLinear(used_coords=cfg["used_coords"]).process(
                    grd_in, sta_in
                )
            elif module_name == "nearest":
                from interp_gs_nearest_plugin import InterpGsNearest

                result = InterpGsNearest().process(grd_in, sta_in)
            elif module_name == "cubic":
                from interp_gs_cubic_plugin import InterpGsCubic

                result = InterpGsCubic().process(grd_in, sta_in)
            else:
                raise ValueError(f"未知 module: {module_name}")

            if result is None:
                raise RuntimeError("插值返回 None：目标站点均在源网格外，或 dtime 范围无交集")
            if cfg["output"]:
                if cfg["output_type"] == "csv":
                    meb.write_stadata_to_csv(
                        result, cfg["output"], creat_dir=True
                    )
                else:
                    meb.write_stadata_to_micaps3(
                        result, cfg["output"], creat_dir=True
                    )
                print("写出 →", cfg["output"])
            print(result)
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return InterpolationGridStationCli().build_parser()


def interpolation_grid_station_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return InterpolationGridStationCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(interpolation_grid_station_cli())
