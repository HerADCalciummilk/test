# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "src" / "mait_3h.py",
        _ROOT / "src" / "mait_3_plugin.py",
        _ROOT / "src" / "mait_3_plugin_util.py",
        _ROOT / "src" / "utils" / "util_env.py",
        _ROOT / "src" / "utils" / "util_new.py",
        _ROOT / "utils" / "__init__.py",
        _ROOT / "resource" / "mait_3.ini",
        _ROOT / "resource" / "para_3_local.ini",
        _ROOT / "resource" / "para_3_background_local.ini",
        _ROOT / "resource" / "para_3_background.ini",
        _ROOT / "README.md",
        _ROOT / "NIMM_list.md",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, "缺少:\n" + "\n".join(missing)


def test_cli_help():
    r = subprocess.run(
        [sys.executable, "-m", "cli", "--help"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "time-inputs" in out or "time-input" in out
    assert "is-multi" in out


def test_import_mait_3h_process():
    from mait_3h import process, RunProcess
    assert callable(process)
    assert RunProcess is not None


def test_import_plugins():
    from mait_3_plugin import (
        AnalysisTsWeightProcess,
        StationDataInterp2GridDataProcess,
        DataFlgProcess,
    )
    assert AnalysisTsWeightProcess is not None
    assert StationDataInterp2GridDataProcess is not None
    assert DataFlgProcess is not None
