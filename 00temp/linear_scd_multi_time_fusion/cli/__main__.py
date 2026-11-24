# -*- coding: utf-8 -*-
"""``python -m cli``：无参数走融合；首项为命令名则转对应 process。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_COMMANDS = {
    "run_scd_fusion": "linear_scd_multi_time_fusion_cli",
    "linear_scd_multi_time_fusion": "linear_scd_multi_time_fusion_cli",
    "split_qpf": "split_qpf_cli",
    "pad_fusion_output": "pad_fusion_output_cli",
}

argv = list(sys.argv[1:])
stem = None
if argv and "=" not in argv[0] and not str(argv[0]).startswith("-"):
    stem = argv.pop(0)
mod_name = _COMMANDS.get(stem, "linear_scd_multi_time_fusion_cli")
if stem is not None and stem not in _COMMANDS:
    print("未知命令: %s。可选 split_qpf、run_scd_fusion、pad_fusion_output" % stem, file=sys.stderr)
    raise SystemExit(2)
process = importlib.import_module(".%s" % mod_name, __package__).process
try:
    result = process(**parse_kv_argv(argv)) if argv else process()
except ValueError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)
if isinstance(result, int) and result:
    raise SystemExit(result)
