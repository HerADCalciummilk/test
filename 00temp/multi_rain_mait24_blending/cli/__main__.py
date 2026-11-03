# -*- coding: utf-8 -*-
"""
24 小时气象预报集成 CLI（``python -m cli`` → ``mait_24h.process``）。

项目根目录执行
--------------
::

    python -m cli --help
    python -m cli --time-inputs=202401010800,202401011200
    python -m cli --time-inputs=202401010800 --predict-valid-list=36,60,84
    python -m cli verify --h5-file=...

模块调用::

    from mait_24h import process
    process(time_inputs=["202401010800"], is_multi=True, pro_count=2)
"""
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


def _cli_converters():
    from clize.parser import value_converter

    @value_converter
    def comma_str_list(s):
        if s is None or not str(s).strip():
            return None
        return [x.strip() for x in str(s).split(",") if x.strip()]

    @value_converter
    def comma_int_list(s):
        if s is None or not str(s).strip():
            return None
        return [int(x.strip()) for x in str(s).split(",") if x.strip()]

    @value_converter
    def comma_float_list(s):
        if s is None or not str(s).strip():
            return None
        return [float(x.strip()) for x in str(s).split(",") if x.strip()]

    @value_converter
    def optional_str(s):
        if s is None or not str(s).strip():
            return None
        return str(s)

    @value_converter
    def optional_bool_cli(s):
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
        raise ValueError("期望布尔：true/false/1/0 等")

    @value_converter
    def optional_int_cli(s):
        if s is None:
            return None
        t = str(s).strip()
        if not t:
            return None
        return int(t)

    return comma_str_list, comma_int_list, comma_float_list, optional_str, optional_bool_cli, optional_int_cli


def _make_cli_entry():
    from clize.runner import Clize
    from mait_24h import process

    (
        comma_str_list, comma_int_list, comma_float_list,
        optional_str, optional_bool_cli, optional_int_cli,
    ) = _cli_converters()

    def run_cli(
        *,
        time_inputs: comma_str_list,
        predict_valid_list: comma_int_list = None,
        para_path: optional_str = None,
        beta_path: optional_str = None,
        is_obs_bjt: optional_bool_cli = None,
        is_multi: optional_bool_cli = None,
        clip_coords: comma_float_list = None,
        pro_count: optional_int_cli = None,
        split_lat: optional_int_cli = None,
        split_lon: optional_int_cli = None,
    ):
        """
        24 小时气象预报集成处理

        :param time_inputs: 起报时间列表（必填），逗号分隔，如 202401010800,202401011200
        :param predict_valid_list: 预报时效列表（小时），逗号分隔，如 36,60,84；省略则读 resource/mait_24.ini
        :param para_path: 模式/实况路径参数文件 para_24.ini 路径；省略则用 ini 中的 para_ini
        :param beta_path: beta 权重文件路径模板（可含 YYYYMMDDHH）；省略则用 ini 中的 bate_file
        :param is_obs_bjt: 实况是否按北京时解释，true/false；省略则用 ini 的 is_obs_bj
        :param is_multi: 多起报是否多进程并行，true/false；省略则用 ini 的 is_multi
        :param clip_coords: 裁剪范围，六浮点逗号分隔 lon0,lon1,lat0,lat1,dlon,dlat；省略则用 ini
        :param pro_count: 多进程并行进程数；省略则读 mait_24.ini 的 pro_count
        :param split_lat: 纬度方向分块数（站点插值分块）；省略则读 mait_24.ini
        :param split_lon: 经度方向分块数（站点插值分块）；省略则读 mait_24.ini
        """
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
        )

    return Clize(run_cli)


def _run_verify(argv: Sequence[str]) -> None:
    saved_argv = sys.argv
    try:
        sys.argv = [saved_argv[0], *argv]
        from cli.verify import main as verify_main

        verify_main()
    finally:
        sys.argv = saved_argv


def main(argv: Optional[Sequence[str]] = None) -> None:
    """解析命令行并调用 ``mait_24h.process``。"""
    from clize.runner import run

    if argv is not None:
        saved = sys.argv
        try:
            sys.argv = [saved[0], *argv]
            run(_make_cli_entry())
        finally:
            sys.argv = saved
    else:
        run(_make_cli_entry())


if __name__ == "__main__":
    _argv = sys.argv[1:]
    if _argv and _argv[0] == "verify":
        _run_verify(_argv[1:])
    else:
        main()
