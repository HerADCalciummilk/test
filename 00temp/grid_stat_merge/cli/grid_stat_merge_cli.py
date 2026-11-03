# -*- coding: utf-8 -*-
"""格站融合命令行。

在本包目录执行::

    python -m cli --grid=resource/demo_grid.m4 --sta=resource/demo_sta.m3
    python cli/grid_stat_merge_cli.py --grid=resource/demo_grid.m4 --sta=resource/demo_sta.m3
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
from utils.util_env import get_resolved_paths, get_merge_params, set_main_ini

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _parse_bool(s):
    if s is None:
        return None
    t = str(s).strip().lower()
    if t in ("", "none"):
        return None
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔值：true/false/1/0")


def _parse_domain(s):
    if s is None or not str(s).strip():
        return None
    vals = [float(x.strip()) for x in str(s).split(",") if x.strip()]
    if len(vals) != 6:
        raise argparse.ArgumentTypeError("domain 须为 6 个数：sou,nor,wst,est,dlon,dlat")
    return vals


class GridStatMergeCli(CliBase):
    """``grid_stat_merge`` 的命令行。``run`` 转调 ``runner.process``。"""

    description = (
        "grid_stat_merge：格站融合（站点偏差高斯订正网格）。\n"
        "未给出的项从 resource/conf.ini 读取。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli\n"
        "  python -m cli --grid=a.m4 --sta=b.m3 --output=out.m4\n"
        "  python -m cli --R=200 --use-heatflux false\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--grid", dest="grid_path", default=None, metavar="PATH", help="输入格点 Micaps4/NC")
        parser.add_argument("--sta", dest="sta_path", default=None, metavar="PATH", help="输入站点 Micaps3")
        parser.add_argument("--output", dest="output_path", default=None, metavar="PATH", help="输出格点 Micaps4")
        parser.add_argument("--terr", dest="terr_path", default=None, metavar="PATH", help="可选地形格点")
        parser.add_argument("--R", dest="R", type=float, default=None, help="误差传播半径（默认 ini）")
        parser.add_argument(
            "--domain", type=_parse_domain, default=None,
            metavar="sou,nor,wst,est,dlon,dlat",
            help="业务域；省略则从格点推断或读 ini",
        )
        parser.add_argument(
            "--use-heatflux", dest="b_use_heatflux_equation", type=_parse_bool, default=None, metavar="BOOL",
            help="是否热传导去牛眼",
        )
        parser.add_argument(
            "--hf-iters", dest="hf_eq_iter_nums", type=int, default=None, metavar="N",
            help="热传导迭代次数",
        )
        parser.add_argument("--log-file", dest="log_file", default=None, metavar="PATH", help="日志路径模板")
        parser.add_argument("--grid-type", dest="grid_type", default=None, metavar="TYPE", help="格点格式 m4/nc")
        parser.add_argument("--sta-type", dest="sta_type", default=None, metavar="TYPE", help="站点格式 m3/nc")
        parser.add_argument("--sta-val-col", dest="sta_val_col", default=None, metavar="COL", help="站点数值列名")
        parser.add_argument("--sta-lon-col", dest="sta_lon_col", default=None, metavar="COL", help="站点经度列名")
        parser.add_argument("--sta-lat-col", dest="sta_lat_col", default=None, metavar="COL", help="站点纬度列名")
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        grid_path=None,
        sta_path=None,
        output_path=None,
        terr_path=None,
        R=None,
        domain=None,
        b_use_heatflux_equation=None,
        hf_eq_iter_nums=None,
        log_file=None,
        grid_type=None,
        sta_type=None,
        sta_val_col=None,
        sta_lon_col=None,
        sta_lat_col=None,
        config=None,
    ) -> int:
        if config:
            set_main_ini(config)
        try:
            get_resolved_paths()
            get_merge_params()
            process(
                grid_path=grid_path,
                sta_path=sta_path,
                output_path=output_path,
                terr_path=terr_path,
                R=R,
                domain=domain,
                b_use_heatflux_equation=b_use_heatflux_equation,
                hf_eq_iter_nums=hf_eq_iter_nums,
                log_file=log_file,
                grid_type=grid_type,
                sta_type=sta_type,
                sta_val_col=sta_val_col,
                sta_lon_col=sta_lon_col,
                sta_lat_col=sta_lat_col,
                config=config,
            )
        finally:
            if config:
                set_main_ini(None)
        return 0


def _build_parser():
    return GridStatMergeCli().build_parser()


def grid_stat_merge_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return GridStatMergeCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(grid_stat_merge_cli())
