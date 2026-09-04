"""静态检查：结构门禁与插件形态。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import PackageRef
from l1_review import Finding, check_plugins, check_plugins_on_files, check_structure


def _mid_pkg(name: str = "demo") -> PackageRef:
    return PackageRef(layout="mid", package_id=f"00temp/{name}", mid_root=Path("00temp") / name)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


GOOD_PLUGIN = """
class BasePlugin:
    def __init__(self):
        pass

    def process(self):
        return None


class DemoPlugin(BasePlugin):
    def __init__(self):
        pass

    def process(self, data):
        return data
"""

EMPTY_PROCESS = """
class BasePlugin:
    def __init__(self):
        pass

    def process(self):
        return None


class DemoPlugin(BasePlugin):
    def __init__(self):
        pass

    def process(self, data):
        pass
"""

MISSING_PROCESS = """
class BasePlugin:
    def __init__(self):
        pass

    def process(self):
        return None


class DemoPlugin(BasePlugin):
    def __init__(self):
        pass
"""

ONLY_BASE = """
class BasePlugin:
    def __init__(self):
        pass

    def process(self):
        return None
"""


class StructureTests(unittest.TestCase):
    def test_mid_missing_required_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "00temp" / "demo" / "src").mkdir(parents=True)
            findings: list[Finding] = []
            check_structure(repo, _mid_pkg(), findings)
            ids = {item.rule_id for item in findings}
            self.assertIn("MISSING_REQUIRED_DIR", ids)


class PluginTests(unittest.TestCase):
    def test_ok_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write(repo / "00temp" / "demo" / "src" / "plugin.py", GOOD_PLUGIN)
            findings: list[Finding] = []
            check_plugins(repo, _mid_pkg(), findings)
            self.assertEqual(findings, [])

    def test_empty_and_missing_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write(repo / "00temp" / "demo" / "src" / "plugin.py", EMPTY_PROCESS)
            findings: list[Finding] = []
            check_plugins(repo, _mid_pkg(), findings)
            self.assertTrue(any(i.rule_id == "PLUGIN_EMPTY_PROCESS" for i in findings))

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write(repo / "00temp" / "demo" / "src" / "plugin.py", MISSING_PROCESS)
            findings = []
            check_plugins(repo, _mid_pkg(), findings)
            self.assertTrue(any(i.rule_id == "PLUGIN_MISSING_PROCESS" for i in findings))

    def test_no_concrete_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _write(repo / "00temp" / "demo" / "src" / "base.py", ONLY_BASE)
            findings: list[Finding] = []
            check_plugins(repo, _mid_pkg(), findings)
            self.assertTrue(any(i.rule_id == "NO_CONCRETE_PLUGIN" for i in findings))

    def test_weak_check_does_not_require_a_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            py = repo / "NIMM" / "utils" / "x.py"
            _write(py, "VALUE = 1\n")
            findings: list[Finding] = []
            check_plugins_on_files(repo, [py], findings)
            self.assertFalse(any(i.rule_id == "NO_CONCRETE_PLUGIN" for i in findings))


if __name__ == "__main__":
    unittest.main()
