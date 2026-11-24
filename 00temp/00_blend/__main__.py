# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent
_TEMP = _ROOT.parent
for _path in (str(_TEMP), str(_ROOT)):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(_ROOT))
_cli = _ROOT / "cli" / "00_blend_cli.py"
_spec = importlib.util.spec_from_file_location("_nimm_00_blend_cli", _cli)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
if str(_TEMP) not in sys.path:
    sys.path.insert(1, str(_TEMP))
from utils.nimm_cli import nimm_cli
if __name__ == "__main__":
    raise SystemExit(nimm_cli([_ROOT.name, *sys.argv[1:]]))
