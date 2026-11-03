# -*- coding: utf-8 -*-
"""
3 小时气象预报集成 CLI（``python -m cli`` → ``mait_3h.process``）。

::

    python -m cli --help
    python -m cli --time-inputs=202608200000
    python -m cli --time-inputs=202608200000,202608201200 --is-multi=true --pro-count=4
    python -m cli --time-input=202608200000 --predict-valid-list=3,6,9
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
for _p in (str(_ROOT), str(_SRC)):
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed((str(_ROOT), str(_SRC))):
    sys.path.insert(0, _p)


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


def _build_parser():
    p = argparse.ArgumentParser(
        prog="python -m cli",
        description="3 小时多模式降水 TS 加权集成（时效默认 3–252 / 步长 3）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m cli --time-inputs=202608200000\n"
            "  python -m cli --time-inputs=202608200000,202608201200 --is-multi=true --pro-count=4\n"
            "  python -m cli --time-input=202608200000 --predict-valid-list=3,6,9\n"
            "  python -m cli --time-inputs=202608200000 --para-path=resource/para_3.ini\n\n"
            "模块: from mait_3h import process\n"
            "  process(time_inputs=['202608200000', '202608201200'], is_multi=True, pro_count=4)\n"
        ),
    )
    p.add_argument("--time-inputs", type=_parse_str_list, default=None,
                   metavar="YYYYMMDDHHMM,...",
                   help="UTC 起报列表，写 0000/1200 即出该 00/12Z")
    p.add_argument("--time-input", default=None, metavar="YYYYMMDDHHMM",
                   help="单个 UTC 起报（兼容旧写法）")
    p.add_argument("--predict-valid-list", type=_parse_int_list, default=None,
                   metavar="3,6,9,...", help="预报时效列表；省略读 mait_3.ini")
    p.add_argument("--para-path", default=None, help="模式/实况路径 ini")
    p.add_argument("--background-path", default=None, help="背景格点 Micaps4 路径 ini")
    p.add_argument("--beta-path", default=None, help="beta 路径模板")
    p.add_argument("--is-obs-bjt", type=_parse_bool, default=None, metavar="BOOL",
                   help="实况是否按北京时（+8 h）")
    p.add_argument("--is-interp", type=_parse_bool, default=None, metavar="BOOL",
                   help="写出前是否按 clip_coords 双线性裁剪")
    p.add_argument("--is-multi", type=_parse_bool, default=None, metavar="BOOL",
                   help="多个起报是否多进程（SimpleParallelTool）")
    p.add_argument("--clip-coords", type=_parse_float_list, default=None,
                   metavar="lon0,lon1,lat0,lat1,dlon,dlat")
    p.add_argument("--pro-count", type=int, default=None, help="起报并行进程数")
    return p


def main(argv=None):
    from mait_3h import process

    args = _build_parser().parse_args(argv)
    process(
        time_inputs=args.time_inputs,
        time_input=args.time_input,
        para_path=args.para_path,
        beta_path=args.beta_path,
        background_path=args.background_path,
        is_obs_bjt=args.is_obs_bjt,
        is_interp=args.is_interp,
        is_multi=args.is_multi,
        clip_coords=args.clip_coords,
        pro_count=args.pro_count,
        predict_valid_list=args.predict_valid_list,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
