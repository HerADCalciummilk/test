# -*- coding: utf-8 -*-
"""网格站点融合命令行。

在本包目录执行::

    python -m cli --module idw --sta sta.csv --grid grid.nc
    python cli/interpolation_station_grid_cli.py --module idw --sta sta.m3 --grid grid.m4 --output out.nc
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


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _read_sta_data(path: str, meb, sta_type: str):
    if sta_type == "csv":
        return meb.read_stadata_from_csv(path)
    return meb.read_stadata_from_micaps3(path)


def _write_grid_data(grd, path: str, meb, grid_type: str) -> None:
    out = Path(path)
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    if grid_type == "nc":
        meb.write_griddata_to_nc(grd, str(out), creat_dir=True)
    else:
        meb.write_griddata_to_micaps4(grd, str(out), creat_dir=True)


class InterpolationStationGridCli(CliBase):
    """``interpolation_station_grid`` 的命令行。``run`` 先补齐参数，再调用对应插件。"""

    description = (
        "网格站点融合。\n"
        "用 --module 选择 idw、idw_delta、gaussian、kriging、cressman"
        "（total 为 idw 旧别名）。\n"
        "idw / idw_delta 均走 InterpSgIdw；kriging 走 InterpSgKriging；"
        "cressman 走 InterpSgCressman。\n"
        "站点支持 csv/m3，格点支持 nc/m4；未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module idw "
        "--sta /data/code/nimm/demo_data/input/sta_grid_interp/sta.csv "
        "--grid /data/code/nimm/demo_data/input/sta_grid_interp/grid.nc\n"
        "  python -m cli --module idw --sta sta.m3 --grid grid.m4 --output out.nc\n"
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
        parser.add_argument(
            "--sta",
            default=None,
            help="站点 csv/m3。省略则读 ini，空则报错",
        )
        parser.add_argument(
            "--grid",
            default=None,
            help="格点 nc/m4。取目标网格信息；idw_delta 同时作为背景场。省略则读 ini，空则报错",
        )
        parser.add_argument(
            "--background",
            default=None,
            help="可选背景场 nc/m4。idw/kriging/gaussian 为偏差订正；cressman 为逐步订正初估场。省略则读 ini",
        )
        parser.add_argument(
            "--sta-type",
            default=None,
            metavar="csv|m3",
            help="站点格式。省略则读 ini；再无则按扩展名（.csv→csv，否则 m3）",
        )
        parser.add_argument(
            "--grid-type",
            default=None,
            metavar="nc|m4",
            help="格点格式。省略则读 ini；再无则按扩展名（.nc→nc，否则 m4）",
        )
        parser.add_argument(
            "--background-type",
            default=None,
            metavar="nc|m4",
            help="背景场格式。省略则读 ini；再无则按扩展名",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="可选输出格点路径（nc/m4）。省略则读 ini；留空仅打印",
        )
        parser.add_argument(
            "--output-type",
            default=None,
            metavar="nc|m4",
            help="输出格式。省略则读 ini；再无则按 output 扩展名",
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
        sta_type=None,
        grid_type=None,
        background_type=None,
        output=None,
        output_type=None,
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
                output=output,
                sta_type=sta_type,
                grid_type=grid_type,
                background_type=background_type,
                output_type=output_type,
                config=config,
            )
            import meteva_base as meb

            sta_data = _read_sta_data(cfg["sta"], meb, cfg["sta_type"])
            grid_data = _read_grid_data(cfg["grid"], meb, cfg["grid_type"])
            grid_info = meb.get_grid_of_data(grid_data)

            def _read_background():
                if not cfg["background"]:
                    return None
                return _read_grid_data(
                    cfg["background"], meb, cfg["background_type"]
                )

            if module_name == "idw":
                from interp_sg_idw_plugin import InterpSgIdw

                background_data = _read_background()
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

                result = InterpSgGaussian(halfR=cfg["half_r"]).process(
                    sta_data, grid_info, background=_read_background()
                )
            elif module_name == "kriging":
                from interp_sg_kriging import InterpSgKriging

                result = InterpSgKriging(
                    model=cfg["kriging_model"],
                    sill=cfg["kriging_sill"],
                    range_=cfg["kriging_range"],
                    nugget=cfg["kriging_nugget"],
                    nearNum=cfg["near_num"],
                ).process(sta_data, grid_info, background=_read_background())
            elif module_name == "cressman":
                from interp_sg_cressman_plugin import InterpSgCressman

                result = InterpSgCressman(
                    r_list=cfg["r_list"],
                    nearNum=cfg["near_num"],
                ).process(sta_data, grid_info, background=_read_background())
            else:
                raise ValueError(f"未知 module: {module_name}")

            if result is None:
                raise RuntimeError("插值返回 None")
            if cfg["output"]:
                _write_grid_data(result, cfg["output"], meb, cfg["output_type"])
                print("写出 →", cfg["output"])
            print(result)
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return InterpolationStationGridCli().build_parser()


def interpolation_station_grid_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return InterpolationStationGridCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(interpolation_station_grid_cli())
