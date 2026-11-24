# -*- coding: utf-8 -*-
"""``python -m cli``：无参数走主入口；``train`` / ``apply`` 作为 command。"""
import sys

from .quantile_regression_random_forest_cli import process
from utils.merge_params import parse_kv_argv

argv = list(sys.argv[1:])
extra = {}
if argv and "=" not in argv[0] and not str(argv[0]).startswith("-"):
    extra["command"] = argv.pop(0)
if argv:
    extra.update(parse_kv_argv(argv))
result = process(**extra) if extra else process()
if isinstance(result, int) and result:
    raise SystemExit(result)
