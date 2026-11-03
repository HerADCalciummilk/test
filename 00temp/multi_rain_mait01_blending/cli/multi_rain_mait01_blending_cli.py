# -*- coding: utf-8 -*-
"""1 小时气象预报集成命令行。

在本包目录执行::

    python -m cli --time-inputs=202401010800,202401011200
    python cli/multi_rain_mait01_blending_cli.py --time-inputs=202401010800
    python -m cli verify ts --h5-file=...
"""
import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_ROOT), str(_SRC))):
    sys.path.insert(0, _p)

from utils.cli_base import CliBase

_CONFIG_HELP = "运行配置文件，传给入口函数。相对路径按项目根目录解析。省略则用包内默认 ini。"


def _parse_str_list(s):
    if s is None or not str(s).strip():
        return None
    return [x.strip() for x in str(s).split(",") if x.strip()]


def _parse_int_list(s):
    if s is None or not str(s).strip():
        return None
    return [int(x.strip()) for x in str(s).split(",") if x.strip()]


def _parse_float_list(s):
    if s is None or not str(s).strip():
        return None
    return [float(x.strip()) for x in str(s).split(",") if x.strip()]


def _parse_optional_str(s):
    if s is None or not str(s).strip():
        return None
    return str(s)


def _parse_bool(s):
    if s is None:
        return None
    if isinstance(s, bool):
        return s
    t = str(s).strip().lower()
    if t in ("", "none"):
        return None
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔：true/false/1/0 等")


def _parse_optional_int(s):
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    return int(t)


class MultiRainMait01BlendingCli(CliBase):
    """``multi_rain_mait01_blending`` 的命令行。``run`` 转调 ``mait_1h.process``。"""

    description = (
        "1 小时气象预报集成处理\n"
        "未给出的项从 resource/conf.ini 读取。"
    )
    epilog = (
        "示例:\n"
        "  python -m cli --help\n"
        "  python -m cli --time-inputs=202401010800,202401011200\n"
        "  python -m cli --time-inputs=202401010800 --predict-valid-list=1,2,3\n"
        "  python -m cli verify ts --h5-file=... --grade-list=... --product-list=...\n\n"
        "模块: from mait_1h import process\n"
        "  process(time_inputs=['202401010800'], is_multi=True, pro_count=2)\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--time-inputs", type=_parse_str_list, required=True,
            metavar="YYYYMMDDHHMM,...",
            help="起报时间列表（必填），逗号分隔，如 202401010800,202401011200",
        )
        parser.add_argument(
            "--predict-valid-list", type=_parse_int_list, default=None,
            metavar="1,2,3",
            help="预报时效列表（小时），逗号分隔，如 1,2,3；省略则读 resource/conf.ini",
        )
        parser.add_argument(
            "--para-path", type=_parse_optional_str, default=None,
            help="模式/实况路径参数文件 local.ini / para_1.ini 路径；省略则用 ini 中的 para_path",
        )
        parser.add_argument(
            "--beta-path", type=_parse_optional_str, default=None,
            help="beta 权重文件路径模板（可含 YYYYMMDDHH）；省略则用 ini 中的 beta_path",
        )
        parser.add_argument(
            "--is-obs-bjt", type=_parse_bool, default=None, metavar="BOOL",
            help="实况是否按北京时解释，true/false；省略则用 ini 的 is_obs_bjt",
        )
        parser.add_argument(
            "--is-multi", type=_parse_bool, default=None, metavar="BOOL",
            help="多起报是否多进程并行，true/false；省略则用 ini 的 is_multi",
        )
        parser.add_argument(
            "--clip-coords", type=_parse_float_list, default=None,
            metavar="lon0,lon1,lat0,lat1,dlon,dlat",
            help="裁剪范围，六浮点逗号分隔 lon0,lon1,lat0,lat1,dlon,dlat；省略则用 ini",
        )
        parser.add_argument(
            "--pro-count", type=_parse_optional_int, default=None,
            help="多进程并行进程数；省略则读 conf.ini 的 pro_count",
        )
        parser.add_argument(
            "--split-lat", type=_parse_optional_int, default=None,
            help="纬度方向分块数（站点插值分块）；省略则读 conf.ini",
        )
        parser.add_argument(
            "--split-lon", type=_parse_optional_int, default=None,
            help="经度方向分块数（站点插值分块）；省略则读 conf.ini",
        )
        parser.add_argument(
            "--log-file", type=_parse_optional_str, default=None,
            help="日志路径模板（可含 YYYYMMDD）；省略则用 ini 中的 log_file",
        )
        parser.add_argument(
            "--background-ini", type=_parse_optional_str, default=None,
            help="背景格点路径配置文件；省略则用 ini 中的 background_ini",
        )
        parser.add_argument(
            "--station-info", type=_parse_optional_str, default=None,
            help="站点信息文件；省略则用 ini 中的 station_info",
        )
        parser.add_argument(
            "--mask-dat", type=_parse_optional_str, default=None,
            help="格点掩膜 dat 文件；省略则用 ini 中的 mask_dat",
        )
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        time_inputs=None,
        predict_valid_list=None,
        para_path=None,
        beta_path=None,
        is_obs_bjt=None,
        is_multi=None,
        clip_coords=None,
        pro_count=None,
        split_lat=None,
        split_lon=None,
        log_file=None,
        background_ini=None,
        station_info=None,
        mask_dat=None,
        config=None,
    ) -> int:
        from mait_1h import process

        process(
            time_inputs=time_inputs,
            predict_valid_list=predict_valid_list,
            para_path=para_path,
            beta_path=beta_path,
            is_obs_bjt=is_obs_bjt,
            is_multi=is_multi,
            clip_coords=clip_coords,
            pro_count=pro_count,
            split_lat=split_lat,
            split_lon=split_lon,
            log_file=log_file,
            background_ini=background_ini,
            station_info=station_info,
            mask_dat=mask_dat,
            config=config,
        )
        return 0


def _build_parser():
    return MultiRainMait01BlendingCli().build_parser()


def _run_verify(argv: Sequence[str]) -> None:
    saved_argv = sys.argv
    try:
        sys.argv = [saved_argv[0], *argv]
        from cli.verify import main as verify_main

        verify_main()
    finally:
        sys.argv = saved_argv


def multi_rain_mait01_blending_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "verify":
        _run_verify(args[1:])
        return 0
    return MultiRainMait01BlendingCli().main(None if argv is None else args)


if __name__ == "__main__":
    raise SystemExit(multi_rain_mait01_blending_cli())
