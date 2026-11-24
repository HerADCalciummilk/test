from pathlib import Path


def test_project_layout():
    root = Path(__file__).resolve().parent.parent
    for name in ("src", "cli", "resource", "test", "nbs", "docs", "utils"):
        assert (root / name).is_dir(), f"missing directory: {name}"


def test_core_source_files_exist():
    root = Path(__file__).resolve().parent.parent
    for name in (
        "util_plugin.py",
        "cube_lonlat_to_equal.py",
        "cube_equal_to_lonlat.py",
        "cube_lonlat_to_equal_cartopy.py",
        "cube_equal_to_lonlat_cartopy.py",
        "__init__.py",
    ):
        assert (root / "src" / name).is_file(), f"missing source file: {name}"
    assert (root / "src" / "utils" / "cpt_utils.py").is_file(), "missing src/utils/cpt_utils.py"
    assert not (root / "src" / "utils" / "__init__.py").is_file(), (
        "src/utils must not have __init__.py (merged via package utils)"
    )
    for name in (
        "coordinate_projection_transform_cli.py",
        "coordinate_projection_transform_cartopy_cli.py",
    ):
        assert (root / "cli" / name).is_file(), f"missing cli file: {name}"
    assert (root / "resource" / "sample" / "2026052400.036.m4").is_file(), (
        "missing resource/sample/2026052400.036.m4"
    )


def test_old_modules_removed():
    root = Path(__file__).resolve().parent.parent
    for name in (
        "utilities.py",
        "cube_base.py",
        "grid_meta.py",
        "cube_setup.py",
        "cartopy_cube_regrid.py",
        "cpt_utils.py",
    ):
        assert not (root / "src" / name).is_file(), f"legacy file still present: {name}"
