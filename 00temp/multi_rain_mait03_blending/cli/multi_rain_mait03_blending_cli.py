# -*- coding: utf-8 -*-
"""3 小时气象预报集成命令行。

在本包目录执行::

    python -m cli --time-inputs=202608200000
    python cli/multi_rain_mait03_blending_cli.py --time-inputs=202608200000
"""
from __future__ import annotations

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


def _parse_bool(s):
    if s is None or not str(s).strip():
        return None
    t = str(s).strip().lower()
    if t in ("1", "true", "yes", "y", "on"):
        return True
    if t in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError("期望布尔 true/false")


class MultiRainMait03BlendingCli(CliBase):
    """``multi_rain_mait03_blending`` 的命令行。``run`` 转调 ``mait_3h.process``。"""

    description = "3 小时多模式降水 TS 加权集成（时效默认 3–252 / 步长 3）"
    epilog = (
        "示例:\n"
        "  python -m cli --time-inputs=202608200000\n"
        "  python -m cli --time-inputs=202608200000,202608201200 --is-multi=true --pro-count=4\n"
        "  python -m cli --time-input=202608200000 --predict-valid-list=3,6,9\n"
        "  python -m cli --time-inputs=202608200000 --para-path=resource/para_3.ini\n\n"
        "模块: from mait_3h import process\n"
        "  process(time_inputs=['202608200000', '202608201200'], is_multi=True, pro_count=4)\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--time-inputs", type=_parse_str_list, default=None,
            metavar="YYYYMMDDHHMM,...",
            help="UTC 起报列表，写 0000/1200 即出该 00/12Z",
        )
        parser.add_argument(
            "--time-input", default=None, metavar="YYYYMMDDHHMM",
            help="单个 UTC 起报（兼容旧写法）",
        )
        parser.add_argument(
            "--predict-valid-list", type=_parse_int_list, default=None,
            metavar="3,6,9,...", help="预报时效列表；省略读 conf.ini",
        )
        parser.add_argument("--para-path", default=None, help="模式/实况路径 ini")
        parser.add_argument("--background-path", default=None, help="背景格点 Micaps4 路径 ini")
        parser.add_argument("--beta-path", default=None, help="beta 路径模板")
        parser.add_argument(
            "--is-obs-bjt", type=_parse_bool, default=None, metavar="BOOL",
            help="实况是否按北京时（+8 h）",
        )
        parser.add_argument(
            "--is-interp", type=_parse_bool, default=None, metavar="BOOL",
            help="写出前是否按 clip_coords 双线性裁剪",
        )
        parser.add_argument(
            "--is-multi", type=_parse_bool, default=None, metavar="BOOL",
            help="多个起报是否多进程（SimpleParallelTool）",
        )
        parser.add_argument(
            "--clip-coords", type=_parse_float_list, default=None,
            metavar="lon0,lon1,lat0,lat1,dlon,dlat",
        )
        parser.add_argument("--pro-count", type=int, default=None, help="起报并行进程数")
        parser.add_argument("--log-file", default=None, help="日志路径模板；省略则用 ini 中的 log_file")
        parser.add_argument("--station-info", default=None, help="站点信息文件；省略则用 ini 中的 station_info")
        parser.add_argument("--mask-dat", default=None, help="格点掩膜 dat 文件；省略则用 ini 中的 mask_dat")
        parser.add_argument(
            "--config", dest="config", default=None, metavar="PATH",
            help=_CONFIG_HELP,
        )

    def run(
        self,
        time_inputs=None,
        time_input=None,
        predict_valid_list=None,
        para_path=None,
        background_path=None,
        beta_path=None,
        is_obs_bjt=None,
        is_interp=None,
        is_multi=None,
        clip_coords=None,
        pro_count=None,
        log_file=None,
        station_info=None,
        mask_dat=None,
        config=None,
    ) -> int:
        from mait_3h import process

        process(
            time_inputs=time_inputs,
            time_input=time_input,
            para_path=para_path,
            beta_path=beta_path,
            background_path=background_path,
            is_obs_bjt=is_obs_bjt,
            is_interp=is_interp,
            is_multi=is_multi,
            clip_coords=clip_coords,
            pro_count=pro_count,
            predict_valid_list=predict_valid_list,
            log_file=log_file,
            station_info=station_info,
            mask_dat=mask_dat,
            config=config,
        )
        return 0


def _build_parser():
    return MultiRainMait03BlendingCli().build_parser()


def multi_rain_mait03_blending_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli`` 与直接运行本文件都进这里。"""
    return MultiRainMait03BlendingCli().main(argv)


if __name__ == "__main__":
    raise SystemExit(multi_rain_mait03_blending_cli())
