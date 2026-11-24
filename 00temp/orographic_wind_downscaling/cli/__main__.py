# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑风速订正；``roughness`` 转粗糙度辅料。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_STEMS = {
    "roughness": "roughness_cli",
    "wind": "orographic_wind_downscaling_cli",
}


def _run(module_name, argv):
    module = importlib.import_module("." + module_name, __package__)
    return module.process(**parse_kv_argv(argv))


_args = list(sys.argv[1:])
if not _args:
    from .orographic_wind_downscaling_cli import process

    process()
elif _args[0] in ("-h", "--help"):
    print("用法: python -m cli [wind|roughness] [key=value ...]")
elif _args[0] in _STEMS:
    _run(_STEMS[_args[0]], _args[1:])
else:
    from .orographic_wind_downscaling_cli import process

    process(**parse_kv_argv(_args))
