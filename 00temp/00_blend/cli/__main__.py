# -*- coding: utf-8 -*-
"""``python -m cli`` → 已装饰的 ``process``（合 conf.ini）。"""
import importlib.util
from pathlib import Path

_path = Path(__file__).with_name("00_blend_cli.py")
_spec = importlib.util.spec_from_file_location("_nimm_00_blend_cli", _path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.process()
