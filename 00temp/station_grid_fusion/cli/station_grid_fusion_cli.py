# -*- coding: utf-8 -*-
"""网格站点融合命令行。

在本包目录执行::

    python -m cli --module idw
    python cli/station_grid_fusion_cli.py --module idw
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
        "用 --module 选择 idw、idw_delta、gaussian、kriging、cressman"
        "（total 为 idw 旧别名）。\n"
        "idw / idw_delta 均走 InterpSgIdw；kriging 走 InterpSgKriging；"
        "cressman 走 InterpSgCressman。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module idw "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc\n"
        "  python -m cli --module kriging "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc "
        "--kriging-model spherical --near-num 20\n"
        "  python -m cli --module gaussian "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc "
        "--half-r 20\n"
        "  python -m cli --module cressman "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc "
        "--r-list 60000,40000,20000\n"
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
            choices=["idw", "idw_delta", "gaussian", "kriging", "cressman", "total"],
            help="idw、idw_delta、gaussian、kriging、cressman；total 为 idw 旧别名。省略则读 ini，预设 idw",
        )
        parser.add_argument("--sta", default=None, help="站点 csv。省略则读 ini，空则报错")
        parser.add_argument(
            "--grid",
            default=None,
            help="格点 nc。取目标网格信息；idw_delta 同时作为背景场。省略则读 ini，空则报错",
        )
        parser.add_argument(
            "--background",
            default=None,
            help="可选背景场 nc。idw/kriging/gaussian 为偏差订正；cressman 为逐步订正初估场。省略则读 ini",
        )
        parser.add_argument("--effect-r", type=int, default=None, help="影响/高斯半径。省略则读对应节，预设 1000")
        parser.add_argument("--near-num", type=int, default=None, help="最邻近站点数。省略则读对应节")
        parser.add_argument("--decrease", type=int, default=None, help="距离衰减指数。省略则读对应节，预设 2")
        parser.add_argument("--half-r", type=int, default=None, help="仅 gaussian：高斯半径。省略则读 ini，预设 20")
        parser.add_argument(
            "--r-list",
            default=None,
            metavar="R1,R2,...",
            help="仅 cressman：影响半径列表（米）。省略则读 ini，预设 60000,40000,20000",
        )
        parser.add_argument(
            "--kriging-model",
            default=None,
            choices=["spherical", "exponential", "gaussian"],
            help="仅 kriging：变异函数模型。省略则读 ini，预设 spherical",
        )
        parser.add_argument(
            "--kriging-sill",
            type=float,
            default=None,
            help="仅 kriging：基台值。省略则读 ini；留空则用站点方差自动估计",
        )
        parser.add_argument(
            "--kriging-range",
            type=float,
            default=None,
            help="仅 kriging：变程（与笛卡尔距离同单位）。省略则读 ini；留空则自动估计",
        )
        parser.add_argument(
            "--kriging-nugget",
            type=float,
            default=None,
            help="仅 kriging：块金值。省略则读 ini，预设 0",
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
        r_list=None,
        kriging_model=None,
        kriging_sill=None,
        kriging_range=None,
        kriging_nugget=None,
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
                kriging_model=kriging_model,
                kriging_sill=kriging_sill,
                kriging_range=kriging_range,
                kriging_nugget=kriging_nugget,
                r_list=r_list,
                config=config,
            )
            import meteva_base as meb

            sta_data = meb.read_stadata_from_csv(cfg["sta"])
            grid_data = meb.read_griddata_from_nc(cfg["grid"])
            grid_info = meb.get_grid_of_data(grid_data)
            if module_name == "idw":
                from interp_sg_idw_plugin import InterpSgIdw

                background_data = None
                if cfg["background"]:
                    background_data = meb.read_griddata_from_nc(cfg["background"])
                result = InterpSgIdw(
                    effectR=cfg["effect_r"],
                    nearNum=cfg["near_num"],
                    decrease=cfg["decrease"],
                    gaussian=background_data is not None,
                ).process(sta_data, grid_info, background=background_data)
            elif module_name == "idw_delta":
                from interp_sg_idw_plugin import InterpSgIdw

                result = InterpSgIdw(
                    effectR=cfg["effect_r"],
                    nearNum=cfg["near_num"],
                    decrease=cfg["decrease"],
                    gaussian=True,
                ).process(sta_data, grid_info, background=grid_data)
            elif module_name == "gaussian":
                from interp_sg_gaussian_plugin import InterpSgGaussian

                background_data = None
                if cfg["background"]:
                    background_data = meb.read_griddata_from_nc(cfg["background"])
                result = InterpSgGaussian(halfR=cfg["half_r"]).process(
                    sta_data, grid_info, background=background_data
                )
            elif module_name == "kriging":
                from interp_sg_kriging import InterpSgKriging

                background_data = None
                if cfg["background"]:
                    background_data = meb.read_griddata_from_nc(cfg["background"])
                result = InterpSgKriging(
                    model=cfg["kriging_model"],
                    sill=cfg["kriging_sill"],
                    range_=cfg["kriging_range"],
                    nugget=cfg["kriging_nugget"],
                    nearNum=cfg["near_num"],
                ).process(sta_data, grid_info, background=background_data)
            elif module_name == "cressman":
                from interp_sg_cressman_plugin import InterpSgCressman

                background_data = None
                if cfg["background"]:
                    background_data = meb.read_griddata_from_nc(cfg["background"])
                result = InterpSgCressman(
                    r_list=cfg["r_list"],
                    nearNum=cfg["near_num"],
                ).process(sta_data, grid_info, background=background_data)
            else:
                raise ValueError(f"未知 module: {module_name}")
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
