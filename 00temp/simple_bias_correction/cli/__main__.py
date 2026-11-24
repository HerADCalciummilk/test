# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑主命令；首个 token 命中命令主干则转对应 process。"""
import importlib
import sys

from .simple_bias_correction_cli import process as primary
from utils.merge_params import parse_kv_argv

_COMMANDS = {
    'apply-bias': 'simple_bias_correction_cli',
    'prb_bias_correction': 'simple_bias_correction_cli',
    'simple_bias_correction': 'simple_bias_correction_cli',
    'calc-bias': 'cal_calculate_forecast_bias_cli',
    'cal_calculate_forecast_bias': 'cal_calculate_forecast_bias_cli',
}


def _run():
    argv = list(sys.argv[1:])
    if argv and "=" not in argv[0] and not str(argv[0]).startswith("-"):
        stem = argv[0]
        module_name = _COMMANDS.get(stem)
        if module_name is None:
            known = ", ".join(_COMMANDS)
            raise SystemExit("未知命令: %s。可选: %s" % (stem, known))
        module = importlib.import_module("." + module_name, __package__)
        return module.process(**parse_kv_argv(argv[1:]))
    if argv:
        return primary(**parse_kv_argv(argv))
    return primary()


_run()
