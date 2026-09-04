"""包发现与路径解析。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import (
    discover_packages,
    parse_package_ref,
    path_is_under,
    resolve_path_arg,
)


class ParsePackageRefTests(unittest.TestCase):
    def test_mid_and_official(self) -> None:
        mid = parse_package_ref(Path("00temp/demo/src/a.py"))
        self.assertIsNotNone(mid)
        assert mid is not None
        self.assertEqual(mid.layout, "mid")
        self.assertEqual(mid.package_id, "00temp/demo")

        official = parse_package_ref(Path("NIMM/02diagnostic/demo/plugin.py"))
        self.assertIsNotNone(official)
        assert official is not None
        self.assertEqual(official.layout, "official")
        self.assertEqual(official.package_id, "NIMM/02diagnostic/demo")

        via_cli = parse_package_ref(Path("cli/02diagnostic/demo/run.py"))
        self.assertIsNotNone(via_cli)
        assert via_cli is not None
        self.assertEqual(via_cli.package_id, "NIMM/02diagnostic/demo")

    def test_not_a_package(self) -> None:
        self.assertIsNone(parse_package_ref(Path("NIMM/utils/helper.py")))
        self.assertIsNone(parse_package_ref(Path("NIMM/02diagnostic")))
        self.assertIsNone(parse_package_ref(Path("docs/README.md")))
        self.assertIsNone(parse_package_ref(Path("")))


class ResolvePathArgTests(unittest.TestCase):
    def test_resolve_path_arg(self) -> None:
        repo = Path(".")
        mid = resolve_path_arg(repo, "00temp/demo")
        self.assertIsNotNone(mid)
        assert mid is not None
        self.assertEqual(mid.package_id, "00temp/demo")

        self.assertIsNone(resolve_path_arg(repo, "NIMM/utils"))
        self.assertIsNone(resolve_path_arg(repo, "README.md"))


class DiscoverPackagesTests(unittest.TestCase):
    def test_mid_needs_src_or_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            pkg = repo / "00temp" / "demo"
            pkg.mkdir(parents=True)
            files = [Path("00temp/demo/docs/a.md")]
            self.assertEqual(discover_packages(repo, files), [])

            (pkg / "src").mkdir()
            found = discover_packages(repo, files)
            self.assertEqual([p.package_id for p in found], ["00temp/demo"])

    def test_official_from_companion_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            files = [Path("docs/02diagnostic/demo/README.md")]
            found = discover_packages(repo, files)
            self.assertEqual([p.package_id for p in found], ["NIMM/02diagnostic/demo"])


class PathIsUnderTests(unittest.TestCase):
    def test_nested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            child = root / "pkg" / "a.py"
            child.parent.mkdir(parents=True)
            child.write_text("x", encoding="utf-8")
            self.assertTrue(path_is_under(child, root))
            self.assertFalse(path_is_under(root, child))


if __name__ == "__main__":
    unittest.main()
