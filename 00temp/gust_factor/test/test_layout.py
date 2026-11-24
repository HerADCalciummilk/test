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


def test_process_signature():
    import inspect

    from cli.gust_factor_cli import process

    assert callable(process)
    names = inspect.signature(process).parameters
    for dest in (
        "mode",
        "station_csv_dir",
        "fore_hours",
        "factor_path",
        "u_path",
        "v_path",
        "fore_hour",
        "output_path",
        "make_png",
        "show_png",
        "ws_path",
        "png_path",
        "log_file",
        "config",
    ):
        assert dest in names
