# -*- coding: utf-8 -*-
"""在 ``00temp`` 目录执行 ``python -m frequency_matching_rain24``。"""
import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_TEMP = _ROOT.parent
for _path in (str(_TEMP), str(_ROOT)):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(_ROOT))

# 先导入本包 cli，让本包 utils 完成路径合并，再使用调度器。
importlib.import_module("cli.%s_cli" % _ROOT.name)
if str(_TEMP) not in sys.path:
    sys.path.insert(1, str(_TEMP))

from utils.nimm_cli import nimm_cli


if __name__ == "__main__":
    raise SystemExit(nimm_cli([_ROOT.name, *sys.argv[1:]]))
