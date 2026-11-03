# -*- coding: utf-8 -*-
"""坐标投影转换命令行。

在本包目录执行::

    python -m cli --mode lonlat-to-equal
    python cli/coordinate_projection_transform_cli.py --mode lonlat-to-equal
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import MODES, resolve_args, set_main_ini


class CoordinateProjectionTransformCli(CliBase):
    """``coordinate_projection_transform`` 的命令行。``run`` 转调 ``resolve_args``。"""

    description = (
        "坐标投影转换。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli\n"
        "  python -m cli --mode lonlat-to-equal --grid-distance 5000\n"
        "  python -m cli --mode meteva-to-cube --spatial-grid equalarea\n"
        "  python -m cli --mode lonlat-to-equal\n"
        "  python cli/coordinate_projection_transform_cli.py --mode lonlat-to-equal\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--config",
            default=None,
            metavar="PATH",
            help="运行配置文件，传给入口。相对路径按项目根目录解析。省略则用包内默认 ini。",
        )
        parser.add_argument(
            "--mode",
            choices=MODES,
            default=None,
            help="summary、lonlat-to-equal、meteva-to-cube、cube-to-meteva。省略则读 ini，预设 summary",
        )
        parser.add_argument(
            "--projection-extent",
            default=None,
            help="仅 lonlat-to-equal：lonmin,lonmax,latmin,latmax。省略则读 ini，预设 83,138,12,53",
        )
        parser.add_argument(
            "--secant-latitudes",
            default=None,
            help="仅 lonlat-to-equal：两个割线纬度。省略则读 ini，预设 25,47",
        )
        parser.add_argument(
            "--grid-distance",
            type=float,
            default=None,
            help="仅 lonlat-to-equal：等距格距（米）。省略则读 ini，预设 1000",
        )
        parser.add_argument(
            "--regrid-mode",
            choices=["bilinear", "nearest"],
            default=None,
            help="仅 lonlat-to-equal：插值方式。省略则读 ini，预设 bilinear",
        )
        parser.add_argument(
            "--extrapolation-mode",
            default=None,
            help="仅 lonlat-to-equal：域外填充。省略则读 ini，预设 nanmask",
        )
        parser.add_argument(
            "--spatial-grid",
            choices=["latlon", "equalarea"],
            default=None,
            help="仅 meteva-to-cube：目标投影。省略则读 ini，预设 latlon",
        )
        parser.add_argument(
            "--bounds",
            default=None,
            help="仅 meteva-to-cube：时间界，如 -1,0。省略则读 ini，空表示不设",
        )
        parser.add_argument(
            "--near-num",
            type=int,
            default=None,
            help="KDTree 最邻近点数。省略则读 ini，预设 3",
        )
        parser.add_argument(
            "--near-distance",
            type=float,
            default=None,
            help="KDTree 搜索距离（米）。省略则读 ini，预设 20000",
        )

    def run(
        self,
        mode=None,
        projection_extent=None,
        secant_latitudes=None,
        grid_distance=None,
        regrid_mode=None,
        extrapolation_mode=None,
        spatial_grid=None,
        bounds=None,
        near_num=None,
        near_distance=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            resolved = resolve_args(
                mode=mode,
                projection_extent=projection_extent,
                secant_latitudes=secant_latitudes,
                grid_distance=grid_distance,
                regrid_mode=regrid_mode,
                extrapolation_mode=extrapolation_mode,
                spatial_grid=spatial_grid,
                bounds=bounds,
                near_num=near_num,
                near_distance=near_distance,
                config=config,
            )
            if resolved["mode"] == "summary":
                print("available modes: lonlat-to-equal, meteva-to-cube, cube-to-meteva")
                print("未给出的参数来自 resource/conf.ini，缺项再用预设。")
                return 0

            # 重依赖延后导入，summary 与 --help 不加载 iris / cartopy。
            if resolved["mode"] == "lonlat-to-equal":
                from src.cube_lonlat_to_equal import CubeLonlatToEqual

                print(CubeLonlatToEqual.__name__)
                print(
                    "projection_extent={projection_extent} secant_latitudes={secant_latitudes} "
                    "grid_distance={grid_distance} regrid_mode={regrid_mode} "
                    "extrapolation_mode={extrapolation_mode}".format(**resolved)
                )
            elif resolved["mode"] == "meteva-to-cube":
                from src.cube_base import TransMetevaToCube

                print(TransMetevaToCube.__name__)
                print("spatial_grid={spatial_grid} bounds={bounds}".format(**resolved))
            elif resolved["mode"] == "cube-to-meteva":
                from src.cube_base import TransCubeToMeteva

                print(TransCubeToMeteva.__name__)
                print("near_num={near_num} near_distance={near_distance}".format(**resolved))
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return CoordinateProjectionTransformCli().build_parser()


def coordinate_projection_transform_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return CoordinateProjectionTransformCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(coordinate_projection_transform_cli())
