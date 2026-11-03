# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths_exist():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "src" / "runner.py",
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
    assert "3" in (r.stdout + r.stderr)
