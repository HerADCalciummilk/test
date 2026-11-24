# -*- coding: utf-8 -*-
"""``python -m cli``：无参数走格点融合；``tran_regrid`` 转海陆重网格。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_COMMANDS = {
    "tran_regrid": "tran_regrid_cli",
    "interpolation_grid_grid": "interpolation_grid_grid_cli",
}

argv = list(sys.argv[1:])
stem = None
if argv and "=" not in argv[0] and not str(argv[0]).startswith("-"):
    stem = argv.pop(0)
mod_name = _COMMANDS.get(stem, "interpolation_grid_grid_cli")
if stem is not None and stem not in _COMMANDS:
    print("未知命令: %s。可选 tran_regrid" % stem, file=sys.stderr)
    raise SystemExit(2)
process = importlib.import_module(".%s" % mod_name, __package__).process
try:
    result = process(**parse_kv_argv(argv)) if argv else process()
except ValueError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)
if isinstance(result, int) and result:
    raise SystemExit(result)
