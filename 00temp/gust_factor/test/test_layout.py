# -*- coding: utf-8 -*-
"""仓库布局与关键文件存在性。"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths_exist():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "src" / "gust_factor.py",
        _ROOT / "src" / "utils" / "util_env.py",
        _ROOT / "utils" / "__init__.py",
        _ROOT / "resource" / "gust_factor.ini",
        _ROOT / "README.md",
        _ROOT / "NIMM_list.md",
        _ROOT / "docs" / "gust_factor_程序说明.md",
        _ROOT / "00log" / "gust_factor_整理_20260904.log",
        _ROOT / "00temp" / "gust_factor",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, "缺少路径:\n" + "\n".join(missing)


def test_cli_help_runs():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "cli", "--help"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert r.returncode == 0, r.stderr
    assert "gust_factor" in (r.stdout + r.stderr)
