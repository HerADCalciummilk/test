# -*- coding: utf-8 -*-
"""仓库布局与新入口。"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths_exist():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "cli" / "interp_sg_cressman_cli.py",
        _ROOT / "src" / "interp_sg_cressman_plugin.py",
        _ROOT / "src" / "utils" / "util_env.py",
        _ROOT / "utils" / "__init__.py",
        _ROOT / "resource" / "interp_sg_cressman.ini",
        _ROOT / "README.md",
        _ROOT / "NIMM_list.md",
        _ROOT / "docs" / "interp_sg_cressman_程序说明.md",
        _ROOT / "00log" / "interp_sg_cressman_整理_20260826.log",
        _ROOT / "00temp" / "interp_sg_cressman",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, "缺少路径:\n" + "\n".join(missing)


def test_cli_entry_calls_process():
    text = (_ROOT / "cli" / "__main__.py").read_text(encoding="utf-8")
    assert "from .interp_sg_cressman_cli import process" in text
    assert "process()" in text
    assert "def main(" not in text
