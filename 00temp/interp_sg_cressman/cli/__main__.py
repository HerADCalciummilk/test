# -*- coding: utf-8 -*-
"""
Cressman 站点→格点 CLI：解析参数后调度 ``runner.process``。

项目根目录执行::

    python -m cli --help
    python -m cli --sta=resource/demo_sta.m3 --domain=20,50,70,140,0.1,0.1
    python -m cli --sta=a.m3 --background=b.m4 --output=out.m4
"""
import argparse
import sys
from pathlib import Path


def _bootstrap_paths():
    _root = Path(__file__).resolve().parent.parent
    _src = _root / "src"
    for p in (str(_root), str(_src)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap_paths()

from runner import process
from utils.util_env import get_cressman_params, get_resolved_paths


def _parse_float_list(s, n=None, name="list"):
    if s is None or not str(s).strip():
        return None
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if n is not None and len(vals) != n:
        raise argparse.ArgumentTypeError("%s 须为 %d 个数" % (name, n))
    return vals


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m cli",
        description=(
            "interp_sg_cressman：站点→格点 Cressman 插值。\n"
            "未给出的项从 resource/interp_sg_cressman.ini 读取。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli --help\n"
            "  python -m cli --sta=a.m3 --background=b.m4 --output=out.m4\n"
            "  python -m cli --sta=a.m3 --domain=20,50,70,140,0.1,0.1 --r-list=60000,40000,20000\n"
        ),
    )
    parser.add_argument("--sta", default=None, metavar="PATH", help="输入站点 Micaps3/NC")
    parser.add_argument("--output", default=None, metavar="PATH", help="输出格点 Micaps4")
    parser.add_argument("--background", default=None, metavar="PATH", help="可选背景格点")
    parser.add_argument(
        "--grid-template", default=None, metavar="PATH",
        help="可选网格模板格点（仅取水平网格）",
    )
    parser.add_argument(
        "--r-list", default=None, metavar="R1,R2,...",
        help="Cressman 半径列表（米），如 60000,40000,20000",
    )
    parser.add_argument("--near-num", type=int, default=None, metavar="N", help="KDTree 邻近站点数")
    parser.add_argument(
        "--outer-value", type=float, default=None, metavar="V",
        help="背景场越界填充值",
    )
    parser.add_argument(
        "--glon", default=None, metavar="slon,elon,dlon",
        help="目标经度定义",
    )
    parser.add_argument(
        "--glat", default=None, metavar="slat,elat,dlat",
        help="目标纬度定义",
    )
    parser.add_argument(
        "--domain", default=None, metavar="sou,nor,wst,est,dlon,dlat",
        help="业务域（与 glon/glat 二选一）",
    )
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    get_resolved_paths()
    get_cressman_params()

    r_list = _parse_float_list(args.r_list, name="r-list") if args.r_list else None
    glon = _parse_float_list(args.glon, n=3, name="glon") if args.glon else None
    glat = _parse_float_list(args.glat, n=3, name="glat") if args.glat else None
    domain = _parse_float_list(args.domain, n=6, name="domain") if args.domain else None

    process(
        sta_path=args.sta,
        output_path=args.output,
        background_path=args.background,
        grid_template_path=args.grid_template,
        r_list=r_list,
        nearNum=args.near_num,
        outer_value=args.outer_value,
        glon=glon,
        glat=glat,
        domain=domain,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
