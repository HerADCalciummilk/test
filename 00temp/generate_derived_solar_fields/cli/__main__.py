# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑晴空辐射；``solar-time`` 或 ``cli=`` 选择地方太阳时。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_COMMANDS = {
    "clearsky": "generate_derived_solar_fields_cli",
    "cal_generate_clearsky_solar_radiation": "generate_derived_solar_fields_cli",
    "cal_generate_clearsky_solar_radiation_cli": "generate_derived_solar_fields_cli",
    "generate_derived_solar_fields": "generate_derived_solar_fields_cli",
    "generate_derived_solar_fields_cli": "generate_derived_solar_fields_cli",
    "solar-time": "cal_generate_solar_time_cli",
    "solar_time": "cal_generate_solar_time_cli",
    "cal_generate_solar_time": "cal_generate_solar_time_cli",
    "cal_generate_solar_time_cli": "cal_generate_solar_time_cli",
}


def _resolve(token):
    key = str(token).strip()
    if key.endswith(".py"):
        key = key[:-3]
    if key not in _COMMANDS:
        known = ", ".join(sorted(set(_COMMANDS)))
        raise ValueError("未知命令: %s。可选: %s" % (token, known))
    return _COMMANDS[key]


def _call(module_name, argv):
    mod = importlib.import_module(".%s" % module_name, __package__)
    params = parse_kv_argv(argv) if argv else {}
    return mod.process(**params)


def _dispatch(argv):
    if not argv:
        from .generate_derived_solar_fields_cli import process
        return process()
    head = argv[0]
    if head in ("-h", "--help"):
        print("用法: python -m cli [命令] [key=value ...]")
        print("命令: clearsky, solar-time")
        return 0
    body = head[2:] if str(head).startswith("--") else str(head)
    if "=" in body and body.split("=", 1)[0].replace("-", "_") == "cli":
        params = parse_kv_argv(argv)
        cli = params.pop("cli")
        mod = importlib.import_module(".%s" % _resolve(cli), __package__)
        return mod.process(**params)
    if "=" not in head and not str(head).startswith("-"):
        return _call(_resolve(head), argv[1:])
    from .generate_derived_solar_fields_cli import process
    return process(**parse_kv_argv(argv))


_dispatch(sys.argv[1:])
