# -*- coding: utf-8 -*-
"""``python -m cli``：无参数跑主入口；子命令名或 ``cli=`` 选择其它 process。"""
import importlib
import sys

from utils.merge_params import parse_kv_argv

_COMMANDS = {
    "landmask": "generate_ancillary_cli",
    "anc_generate_landmask_ancillary": "generate_ancillary_cli",
    "anc_generate_landmask_ancillary_cli": "generate_ancillary_cli",
    "generate_ancillary": "generate_ancillary_cli",
    "generate_ancillary_cli": "generate_ancillary_cli",
    "bands": "dsc_generate_topography_bands_mask_cli",
    "dsc_generate_topography_bands_mask": "dsc_generate_topography_bands_mask_cli",
    "dsc_generate_topography_bands_mask_cli": "dsc_generate_topography_bands_mask_cli",
    "weights": "dsc_generate_topographic_zone_weights_cli",
    "dsc_generate_topographic_zone_weights": "dsc_generate_topographic_zone_weights_cli",
    "dsc_generate_topographic_zone_weights_cli": "dsc_generate_topographic_zone_weights_cli",
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
        from .generate_ancillary_cli import process
        return process()
    head = argv[0]
    if head in ("-h", "--help"):
        print("用法: python -m cli [命令] [key=value ...]")
        print("命令: landmask, bands, weights")
        return 0
    body = head[2:] if str(head).startswith("--") else str(head)
    if "=" in body and body.split("=", 1)[0].replace("-", "_") == "cli":
        params = parse_kv_argv(argv)
        cli = params.pop("cli")
        mod = importlib.import_module(".%s" % _resolve(cli), __package__)
        return mod.process(**params)
    if "=" not in head and not str(head).startswith("-"):
        return _call(_resolve(head), argv[1:])
    from .generate_ancillary_cli import process
    return process(**parse_kv_argv(argv))


_dispatch(sys.argv[1:])
