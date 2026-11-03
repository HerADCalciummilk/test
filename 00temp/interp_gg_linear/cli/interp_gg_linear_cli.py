# -*- coding: utf-8 -*-
"""格点→格点双线性插值命令行。

在本包目录执行::

    python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1
    python cli/interp_gg_linear_cli.py --grid=a.m4 --domain=20,50,70,140,0.1,0.1
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence


def _bootstrap_paths():
    _root = Path(__file__).resolve().parent.parent
    _src = _root / "src"
    for p in (str(_root), str(_src)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap_paths()

from runner import process
from utils.cli_base import CliBase
from utils.util_env import get_linear_params, get_resolved_paths, set_main_ini

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _parse_float_list(s, n=None, name="list"):
    if s is None or not str(s).strip():
        return None
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if n is not None and len(vals) != n:
        raise argparse.ArgumentTypeError("%s 须为 %d 个数" % (name, n))
    return vals


class InterpGgLinearCli(CliBase):
    """``interp_gg_linear`` 的命令行。``run`` 转调 ``runner.process``。"""

    description = (
        "interp_gg_linear：格点→格点双线性插值。\n"
        "未给出的项从 resource/conf.ini 读取。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1 --output=out.m4\n"
        "  python -m cli --grid=a.m4 --glon=70,140,0.1 --glat=15,55,0.1 --outer-value=0\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--grid", dest="grid_path", default=None, metavar="PATH", help="输入源格点 Micaps4/NC")
        parser.add_argument("--output", dest="output_path", default=None, metavar="PATH", help="输出格点 Micaps4")
        parser.add_argument(
            "--grid-template", dest="grid_template_path", default=None, metavar="PATH",
            help="可选网格模板格点（仅取水平网格）",
        )
        parser.add_argument(
            "--used-coords", dest="used_coords", default=None, metavar="xy",
            help="插值坐标，当前仅支持 xy",
        )
        parser.add_argument(
            "--outer-value", dest="outer_value", type=float, default=None, metavar="V",
            help="目标超出源网格时的填充值",
        )
        parser.add_argument(
            "--glon", dest="glon", default=None, metavar="slon,elon,dlon",
            help="目标经度定义",
        )
        parser.add_argument(
            "--glat", dest="glat", default=None, metavar="slat,elat,dlat",
            help="目标纬度定义",
        )
        parser.add_argument(
            "--domain", dest="domain", default=None, metavar="sou,nor,wst,est,dlon,dlat",
            help="业务域（与 glon/glat 二选一）",
        )
        parser.add_argument("--log-file", dest="log_file", default=None, metavar="PATH", help="日志路径模板")
        parser.add_argument("--grid-type", dest="grid_type", default=None, metavar="TYPE", help="源格点格式 m4/nc")
        parser.add_argument(
            "--grid-template-type", dest="grid_template_type", default=None, metavar="TYPE",
            help="网格模板格式 m4/nc",
        )
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        grid_path=None,
        output_path=None,
        grid_template_path=None,
        used_coords=None,
        outer_value=None,
        glon=None,
        glat=None,
        domain=None,
        log_file=None,
        grid_type=None,
        grid_template_type=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            get_resolved_paths()
            get_linear_params()
            glon_v = _parse_float_list(glon, n=3, name="glon") if glon else None
            glat_v = _parse_float_list(glat, n=3, name="glat") if glat else None
            domain_v = _parse_float_list(domain, n=6, name="domain") if domain else None
            process(
                grid_path=grid_path,
                output_path=output_path,
                grid_template_path=grid_template_path,
                used_coords=used_coords,
                outer_value=outer_value,
                glon=glon_v,
                glat=glat_v,
                domain=domain_v,
                log_file=log_file,
                grid_type=grid_type,
                grid_template_type=grid_template_type,
                config=config,
            )
        finally:
            if config:
                set_main_ini(None)
        return 0


def _build_parser():
    return InterpGgLinearCli().build_parser()


def interp_gg_linear_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return InterpGgLinearCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(interp_gg_linear_cli())
