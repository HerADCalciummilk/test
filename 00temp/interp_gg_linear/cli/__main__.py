# -*- coding: utf-8 -*-
"""
格点→格点双线性插值 CLI：解析参数后调度 ``runner.process``。

项目根目录执行::

    python -m cli --help
    python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1
    python -m cli --grid=a.m4 --grid-template=b.m4 --output=out.m4
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
from utils.util_env import get_linear_params, get_resolved_paths


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
            "interp_gg_linear：格点→格点双线性插值。\n"
            "未给出的项从 resource/interp_gg_linear.ini 读取。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli --help\n"
            "  python -m cli --grid=a.m4 --domain=20,50,70,140,0.1,0.1 --output=out.m4\n"
            "  python -m cli --grid=a.m4 --glon=70,140,0.1 --glat=15,55,0.1 --outer-value=0\n"
        ),
    )
    parser.add_argument("--grid", default=None, metavar="PATH", help="输入源格点 Micaps4/NC")
    parser.add_argument("--output", default=None, metavar="PATH", help="输出格点 Micaps4")
    parser.add_argument(
        "--grid-template", default=None, metavar="PATH",
        help="可选网格模板格点（仅取水平网格）",
    )
    parser.add_argument(
        "--used-coords", default=None, metavar="xy",
        help="插值坐标，当前仅支持 xy",
    )
    parser.add_argument(
        "--outer-value", type=float, default=None, metavar="V",
        help="目标超出源网格时的填充值",
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
    get_linear_params()

    glon = _parse_float_list(args.glon, n=3, name="glon") if args.glon else None
    glat = _parse_float_list(args.glat, n=3, name="glat") if args.glat else None
    domain = _parse_float_list(args.domain, n=6, name="domain") if args.domain else None

    process(
        grid_path=args.grid,
        output_path=args.output,
        grid_template_path=args.grid_template,
        used_coords=args.used_coords,
        outer_value=args.outer_value,
        glon=glon,
        glat=glat,
        domain=domain,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
