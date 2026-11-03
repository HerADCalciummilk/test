# -*- coding: utf-8 -*-
"""Cressman 站点→格点命令行。

在本包目录执行::

    python -m cli --sta=resource/demo_sta.m3 --domain=20,50,70,140,0.1,0.1
    python cli/interp_sg_cressman_cli.py --sta=resource/demo_sta.m3 --domain=20,50,70,140,0.1,0.1
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
from utils.util_env import get_cressman_params, get_resolved_paths, set_main_ini

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _parse_float_list(s, n=None, name="list"):
    if s is None or not str(s).strip():
        return None
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if n is not None and len(vals) != n:
        raise argparse.ArgumentTypeError("%s 须为 %d 个数" % (name, n))
    return vals


class InterpSgCressmanCli(CliBase):
    """``interp_sg_cressman`` 的命令行。``run`` 转调 ``runner.process``。"""

    description = (
        "interp_sg_cressman：站点→格点 Cressman 插值。\n"
        "未给出的项从 resource/conf.ini 读取。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli --sta=a.m3 --background=b.m4 --output=out.m4\n"
        "  python -m cli --sta=a.m3 --domain=20,50,70,140,0.1,0.1 --r-list=60000,40000,20000\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--sta", dest="sta_path", default=None, metavar="PATH", help="输入站点 Micaps3/NC")
        parser.add_argument("--output", dest="output_path", default=None, metavar="PATH", help="输出格点 Micaps4")
        parser.add_argument("--background", dest="background_path", default=None, metavar="PATH", help="可选背景格点")
        parser.add_argument(
            "--grid-template", dest="grid_template_path", default=None, metavar="PATH",
            help="可选网格模板格点（仅取水平网格）",
        )
        parser.add_argument(
            "--r-list", dest="r_list", default=None, metavar="R1,R2,...",
            help="Cressman 半径列表（米），如 60000,40000,20000",
        )
        parser.add_argument("--near-num", dest="nearNum", type=int, default=None, metavar="N", help="KDTree 邻近站点数")
        parser.add_argument(
            "--outer-value", dest="outer_value", type=float, default=None, metavar="V",
            help="背景场越界填充值",
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
        parser.add_argument("--sta-type", dest="sta_type", default=None, metavar="TYPE", help="站点格式 m3/nc")
        parser.add_argument(
            "--background-type", dest="background_type", default=None, metavar="TYPE",
            help="背景格点格式 m4/nc",
        )
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
        sta_path=None,
        output_path=None,
        background_path=None,
        grid_template_path=None,
        r_list=None,
        nearNum=None,
        outer_value=None,
        glon=None,
        glat=None,
        domain=None,
        log_file=None,
        sta_type=None,
        background_type=None,
        grid_template_type=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            get_resolved_paths()
            get_cressman_params()
            r_list_v = _parse_float_list(r_list, name="r-list") if r_list else None
            glon_v = _parse_float_list(glon, n=3, name="glon") if glon else None
            glat_v = _parse_float_list(glat, n=3, name="glat") if glat else None
            domain_v = _parse_float_list(domain, n=6, name="domain") if domain else None
            process(
                sta_path=sta_path,
                output_path=output_path,
                background_path=background_path,
                grid_template_path=grid_template_path,
                r_list=r_list_v,
                nearNum=nearNum,
                outer_value=outer_value,
                glon=glon_v,
                glat=glat_v,
                domain=domain_v,
                log_file=log_file,
                sta_type=sta_type,
                background_type=background_type,
                grid_template_type=grid_template_type,
                config=config,
            )
        finally:
            if config:
                set_main_ini(None)
        return 0


def _build_parser():
    return InterpSgCressmanCli().build_parser()


def interp_sg_cressman_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return InterpSgCressmanCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(interp_sg_cressman_cli())
