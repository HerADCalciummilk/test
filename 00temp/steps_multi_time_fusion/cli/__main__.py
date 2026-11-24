# -*- coding: utf-8 -*-
"""``python -m cli``：无参数走主入口；首项为命令名则转对应 process。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_COMMANDS = {
    "noise": "noise_cli",
    "blending": "blending_cli",
    "skill": "climatological_skill_cli",
    "climatological_skill": "climatological_skill_cli",
    "steps_multi_time_fusion": "steps_multi_time_fusion_cli",
}

argv = list(sys.argv[1:])
stem = None
if argv and "=" not in argv[0] and not str(argv[0]).startswith("-"):
    stem = argv.pop(0)
mod_name = _COMMANDS.get(stem, "steps_multi_time_fusion_cli")
if stem is not None and stem not in _COMMANDS:
    print(
        "未知命令: %s。可选 noise、climatological_skill、blending" % stem,
        file=sys.stderr,
    )
    raise SystemExit(2)
process = importlib.import_module(".%s" % mod_name, __package__).process
try:
    result = process(**parse_kv_argv(argv)) if argv else process()
except ValueError as exc:
    print(exc, file=sys.stderr)
    raise SystemExit(1)
if isinstance(result, int) and result:
    raise SystemExit(result)
