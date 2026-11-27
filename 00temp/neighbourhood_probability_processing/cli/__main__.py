# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑主命令；首个 token 命中命令主干则转对应 process。"""
import importlib
import sys

from .neighbourhood_probability_processing_cli import process as primary
from utils.merge_params import from_argv

_COMMANDS = {
    'neighbourhood_probability_processing': 'neighbourhood_probability_processing_cli',
    'ens_nbhood_land_and_sea': 'ens_nbhood_land_and_sea_cli',
    'ens_nbhood_iterate_with_mask': 'ens_nbhood_iterate_with_mask_cli',
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
        return from_argv(module.process, argv=argv[1:])()
    return from_argv(primary, argv=argv)()


_run()
