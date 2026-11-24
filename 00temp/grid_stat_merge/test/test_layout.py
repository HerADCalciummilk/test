# -*- coding: utf-8 -*-
"""仓库布局与关键文件存在性。"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_required_paths_exist():
    required = [
        _ROOT / "cli" / "__main__.py",
        _ROOT / "src" / "runner.py",
        _ROOT / "src" / "grid_stat_merge.py",
        _ROOT / "src" / "utils" / "util_env.py",
        _ROOT / "utils" / "__init__.py",
        _ROOT / "resource" / "grid_stat_merge.ini",
        _ROOT / "README.md",
        _ROOT / "NIMM_list.md",
        _ROOT / "docs" / "grid_stat_merge_程序说明.md",
        _ROOT / "00log" / "grid_stat_merge_整理_20260826.log",
        _ROOT / "00temp" / "grid_stat_merge",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, "缺少路径:\n" + "\n".join(missing)


def test_process_signature():
    import inspect

    from cli.grid_stat_merge_cli import process

    assert callable(process)
    names = inspect.signature(process).parameters
    for dest in (
        "grid_path",
        "sta_path",
        "output_path",
        "terr_path",
        "R",
        "domain",
        "b_use_heatflux_equation",
        "hf_eq_iter_nums",
        "log_file",
        "grid_type",
        "sta_type",
        "sta_val_col",
        "sta_lon_col",
        "sta_lat_col",
        "config",
    ):
        assert dest in names
