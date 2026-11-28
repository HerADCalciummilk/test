import importlib.util
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location(
    "resource_paths", Path(__file__).resolve().parents[1] / "src/core/resource_paths.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_standard_layout():
    project = Path(__file__).resolve().parents[1]
    root, name, terrain = module.resolve_resources(project)
    assert root == project / "resource"
    assert name == "config"
    assert (terrain / "China_5km/Terrain_5km.tif").is_file()


def test_legacy_layout():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "Parameter").mkdir()
        (root / "lib/terrain").mkdir(parents=True)
        assert module.resolve_resources(root) == (root, "Parameter", root / "lib/terrain")
