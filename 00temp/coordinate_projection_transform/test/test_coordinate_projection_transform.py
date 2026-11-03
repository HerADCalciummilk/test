from pathlib import Path


def test_project_layout():
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"


def test_core_source_files_exist():
    root = Path(__file__).resolve().parent.parent
    for name in ("cube_base.py", "cube_lonlat_to_equal.py", "utilities.py", "__init__.py"):
        assert (root / "src" / name).is_file(), f"missing source file: {name}"
