# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑主命令；首个 token 命中命令主干则转对应 process。"""
import importlib
import sys

from .probability_reliability_correction_cli import process as primary
from utils.merge_params import parse_kv_argv

_COMMANDS = {
    'apply': 'probability_reliability_correction_cli',
    'prb_apply_reliability_calibration': 'probability_reliability_correction_cli',
    'probability_reliability_correction': 'probability_reliability_correction_cli',
    'construct': 'prb_construct_reliability_tables_cli',
    'prb_construct_reliability_tables': 'prb_construct_reliability_tables_cli',
    'aggregate': 'prb_aggregate_reliability_tables_cli',
    'prb_aggregate_reliability_tables': 'prb_aggregate_reliability_tables_cli',
    'manipulate': 'prb_manipulate_reliability_table_cli',
    'prb_manipulate_reliability_table': 'prb_manipulate_reliability_table_cli',
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
