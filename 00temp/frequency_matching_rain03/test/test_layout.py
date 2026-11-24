# -*- coding: utf-8 -*-
from pathlib import Path
import importlib

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths_exist():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "src" / "frequency_matching_rain03_plugin.py",
        _ROOT / "src" / "frequency_matching_rain03_plugin_util.py",
        _ROOT / "cli" / "frequency_matching_rain03_cli.py",
        _ROOT / "src" / "proc" / "frequency_match.py",
        _ROOT / "src" / "utils" / "util_env.py",
        _ROOT / "utils" / "__init__.py",
        _ROOT / "resource" / "qpf_fm.ini",
        _ROOT / "resource" / "path.json",
        _ROOT / "README.md",
        _ROOT / "NIMM_list.md",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, "缺少:\n" + "\n".join(missing)


def test_cli_process_importable():
    mod = importlib.import_module("cli.frequency_matching_rain03_cli")
    assert callable(getattr(mod, "process", None))
    assert callable(getattr(mod, "_process", None))
    assert "3" in (mod.__doc__ or "")
