# -*- coding: utf-8 -*-
"""网格站点融合命令行。

在本包目录执行::

    python -m cli --module total
    python cli/station_grid_fusion_cli.py --module total
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths() -> None:
    root = Path(__file__).resolve().parent.parent
    for path in (str(root / "src"), str(root)):
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_args, resolve_module, set_main_ini


class StationGridFusionCli(CliBase):
    """``station_grid_fusion`` 的命令行。``run`` 先补齐参数，再调用对应插件。"""

    description = (
        "网格站点融合。\n"
        "用 --module 选择 total、idw、idw_delta、gaussian。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module total "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc\n"
        "  python -m cli --module idw_delta "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc\n"
        "  python -m cli --module gaussian "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc "
        "--half-r 20\n"
        "  python -m cli --module total\n"
        "  python cli/station_grid_fusion_cli.py --module total\n"
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
            choices=["total", "idw", "idw_delta", "gaussian"],
            help="total、idw、idw_delta、gaussian。省略则读 ini，预设 total",
        )
        parser.add_argument("--sta", default=None, help="站点 csv。省略则读 ini，空则报错")
        parser.add_argument("--grid", default=None, help="格点 nc。idw 用来取格点信息，其余模块作为背景场。省略则读 ini，空则报错")
        parser.add_argument(
            "--background",
            default=None,
            help="仅 total：背景场 nc。省略则读 ini，空表示只做站点到格点插值",
        )
        parser.add_argument("--effect-r", type=int, default=None, help="影响半径。省略则读对应节，预设 1000")
        parser.add_argument("--near-num", type=int, default=None, help="最邻近站点数。省略则读对应节，预设 8")
        parser.add_argument("--decrease", type=int, default=None, help="距离衰减指数。省略则读对应节，预设 2")
        parser.add_argument("--half-r", type=int, default=None, help="仅 gaussian：高斯半径。省略则读 ini，预设 20")
        parser.add_argument(
            "--delta-effect-r",
            type=int,
            default=None,
            help="仅 total 且有背景场：偏差影响半径。省略则读 ini，预设 400",
        )
        parser.add_argument(
            "--delta-near-num",
            type=int,
            default=None,
            help="仅 total 且有背景场：最邻近站点数。省略则读 ini，预设 10",
        )
        parser.add_argument(
            "--delta-decrease",
            type=int,
            default=None,
            help="仅 total 且有背景场：距离衰减指数。省略则读 ini，预设 2",
        )

    def run(
        self,
        module=None,
        sta=None,
        grid=None,
        background=None,
        effect_r=None,
        near_num=None,
        decrease=None,
        half_r=None,
        delta_effect_r=None,
        delta_near_num=None,
        delta_decrease=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            module_name = resolve_module(module, config=config)
            cfg = resolve_args(
                module=module_name,
                sta=sta,
                grid=grid,
                background=background,
                effect_r=effect_r,
                near_num=near_num,
                decrease=decrease,
                half_r=half_r,
                delta_effect_r=delta_effect_r,
                delta_near_num=delta_near_num,
                delta_decrease=delta_decrease,
                config=config,
            )
            import meteva_base as meb

            sta_data = meb.read_stadata_from_csv(cfg["sta"])
            grid_data = meb.read_griddata_from_nc(cfg["grid"])
            if module_name == "idw":
                from interp_sg_idw_plugin import InterpSgIdw

                result = InterpSgIdw(
                    effectR=cfg["effect_r"],
                    nearNum=cfg["near_num"],
                    decrease=cfg["decrease"],
                ).process(sta_data, meb.get_grid_of_data(grid_data))
            elif module_name == "idw_delta":
                from interp_sg_idw_delta_plugin import InterpSgIdwDelta

                result = InterpSgIdwDelta(
                    effectR=cfg["effect_r"],
                    nearNum=cfg["near_num"],
                    decrease=cfg["decrease"],
                ).process(sta_data, grid_data)
            elif module_name == "gaussian":
                from interp_sg_delta_gaussian_plugin import InterpSgDeltaGaussian

                result = InterpSgDeltaGaussian(halfR=cfg["half_r"]).process(sta_data, grid_data)
            else:
                from interp_sg_total_plugin import InterpSgTotal

                background_data = None
                if cfg["background"]:
                    background_data = meb.read_griddata_from_nc(cfg["background"])
                result = InterpSgTotal().process(
                    sta_data,
                    meb.get_grid_of_data(grid_data),
                    grid_background=background_data,
                    effectR=cfg["effect_r"],
                    nearNum=cfg["near_num"],
                    decrease=cfg["decrease"],
                    delta_effectR=cfg["delta_effect_r"],
                    delta_nearNum=cfg["delta_near_num"],
                    delta_decrease=cfg["delta_decrease"],
                )
            print(result)
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return StationGridFusionCli().build_parser()


def station_grid_fusion_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return StationGridFusionCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(station_grid_fusion_cli())
