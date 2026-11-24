# -*- coding: utf-8 -*-
"""``python -m cli``：无参数估计订正因子；``apply`` 转应用订正。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_STEMS = {
    "estimate": "station_height_difference_correction_cli",
    "apply": "apply_cli",
}


def _run(module_name, argv):
    module = importlib.import_module("." + module_name, __package__)
    return module.process(**parse_kv_argv(argv))


_args = list(sys.argv[1:])
if not _args:
    from .station_height_difference_correction_cli import process

    process()
elif _args[0] in ("-h", "--help"):
    print("用法: python -m cli [estimate|apply] [key=value ...]")
elif _args[0] in _STEMS:
    _run(_STEMS[_args[0]], _args[1:])
else:
    from .station_height_difference_correction_cli import process

    process(**parse_kv_argv(_args))
