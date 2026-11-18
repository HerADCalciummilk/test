# -*- coding: utf-8 -*-
"""格点→格点融合命令行。

在本包目录执行::

    python -m cli --module linear --grid a.nc --domain 20,50,70,140,0.1,0.1
    python cli/interpolation_grid_grid_cli.py --module linear --grid a.nc --glon 70,140,0.1 --glat 15,55,0.1
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
    # 包根必须先于 src，否则 import utils 会命中 src/utils
    for path in (src, root_s):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, src)
    sys.path.insert(0, root_s)


_bootstrap_paths()

from utils.cli_base import CliBase
from utils.util_env import resolve_args, resolve_module, set_main_ini


def _parse_float_list(s, n=None, name="list"):
    if s is None or not str(s).strip():
        return None
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if n is not None and len(vals) != n:
        raise argparse.ArgumentTypeError("%s 须为 %d 个数" % (name, n))
    return vals


def _read_grid_data(path: str, meb, grid_type: str):
    if grid_type == "nc":
        return meb.read_griddata_from_nc(path)
    return meb.read_griddata_from_micaps4(path)


def _resolve_target_grid(cfg: dict, meb):
    if cfg["glon"] is not None and cfg["glat"] is not None:
        return meb.basicdata.grid(cfg["glon"], cfg["glat"])
    if cfg["domain"] is not None:
        sou, nor, wst, est, dlon, dlat = cfg["domain"]
        return meb.basicdata.grid([wst, est, dlon], [sou, nor, dlat])
    tmpl = _read_grid_data(cfg["grid_template"], meb, cfg["grid_template_type"])
    g0 = meb.get_grid_of_data(tmpl)
    return meb.basicdata.grid(g0.glon, g0.glat)


class InterpolationGridGridCli(CliBase):
    """``interpolation_grid_grid`` 的命令行。``run`` 先补齐参数，再调用对应插件。"""

    description = (
        "格点→格点融合。\n"
        "用 --module 选择 linear、nearest、cubic。\n"
        "未给出的项先读 resource/conf.ini，再没有则用预设。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli --module linear --grid a.nc "
        "--domain 20,50,70,140,0.1,0.1 --outer-value 0\n"
        "  python -m cli --module nearest --grid a.nc "
        "--domain 20,50,70,140,0.1,0.1 --outer-value 0\n"
        "  python -m cli --module cubic --grid a.m4 "
        "--glon 70,140,0.1 --glat 15,55,0.1 --output out.m4\n"
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
        parser.add_argument(
            "--grid-template",
            default=None,
            help="可选目标网格模板格点。与 glon/glat、domain 三选一",
        )
        parser.add_argument(
            "--grid-type",
            default=None,
            metavar="nc|m4",
            help="源格点格式。省略则读 ini；再无则按扩展名（.nc→nc，否则 m4）",
        )
        parser.add_argument(
            "--grid-template-type",
            default=None,
            metavar="nc|m4",
            help="网格模板格式。省略则读 ini；再无则按扩展名（.nc→nc，否则 m4）",
        )
        parser.add_argument("--output", default=None, help="可选输出 Micaps4 路径")
        parser.add_argument(
            "--outer-value",
            type=float,
            default=None,
            help="目标超出源网格时的填充值。省略则读 ini，预设 0",
        )
        parser.add_argument(
            "--glon",
            default=None,
            metavar="slon,elon,dlon",
            help="目标经度定义",
        )
        parser.add_argument(
            "--glat",
            default=None,
            metavar="slat,elat,dlat",
            help="目标纬度定义",
        )
        parser.add_argument(
            "--domain",
            default=None,
            metavar="sou,nor,wst,est,dlon,dlat",
            help="业务域（与 glon/glat 二选一）",
        )

    def run(
        self,
        module=None,
        grid=None,
        grid_template=None,
        grid_type=None,
        grid_template_type=None,
        output=None,
        outer_value=None,
        glon=None,
        glat=None,
        domain=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            module_name = resolve_module(module, config=config)
            cfg = resolve_args(
                module=module_name,
                grid=grid,
                grid_template=grid_template,
                output=output,
                outer_value=outer_value,
                glon=_parse_float_list(glon, n=3, name="glon") if glon else glon,
                glat=_parse_float_list(glat, n=3, name="glat") if glat else glat,
                domain=_parse_float_list(domain, n=6, name="domain") if domain else domain,
                grid_type=grid_type,
                grid_template_type=grid_template_type,
                config=config,
            )
            import meteva_base as meb

            grd_in = _read_grid_data(cfg["grid"], meb, cfg["grid_type"])
            target = _resolve_target_grid(cfg, meb)

            if module_name == "linear":
                from interp_gg_linear_plugin import InterpGgLinear

                result = InterpGgLinear(outer_value=cfg["outer_value"]).process(
                    grd_in, target
                )
            elif module_name == "nearest":
                from interp_gg_nearest_plugin import InterpGgNearest

                result = InterpGgNearest(outer_value=cfg["outer_value"]).process(
                    grd_in, target
                )
            elif module_name == "cubic":
                from interp_gg_cubic_plugin import InterpGgCubic

                result = InterpGgCubic(outer_value=cfg["outer_value"]).process(
                    grd_in, target
                )
            else:
                raise ValueError(f"未知 module: {module_name}")

            if result is None:
                raise RuntimeError("插值返回 None：目标超出源网格时请设置 --outer-value")
            if cfg["output"]:
                out = Path(cfg["output"])
                if out.parent and str(out.parent) not in ("", "."):
                    out.parent.mkdir(parents=True, exist_ok=True)
                meb.write_griddata_to_micaps4(result, str(out), creat_dir=True)
                print("写出 →", out)
            print(result)
            return 0
        finally:
            if config:
                set_main_ini(None)


def build_parser() -> argparse.ArgumentParser:
    return InterpolationGridGridCli().build_parser()


def interpolation_grid_grid_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return InterpolationGridGridCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(interpolation_grid_grid_cli())
