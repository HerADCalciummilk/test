"""local_review 基础自测（不调用外网）。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_review.dependency_check import check_dependencies
from local_review.docstring_check import check_docstrings
from local_review.meb_check import check_meb_grid
from local_review.models import ReviewReport
from local_review.package import parse_package_path
from local_review.report import render_markdown
from local_review.run_check import run_execution_checks
from local_review.static_checks import check_plugins, check_structure


def _mid_tree(root: Path, pkg: str = "demo") -> Path:
    base = root / "00temp" / pkg
    for name in ("src", "cli", "test", "docs", "nbs", "resource"):
        (base / name).mkdir(parents=True)
        (base / name / ".gitkeep").write_text("", encoding="utf-8")
    return base


PLUGIN_OK = '''"""demo module."""

class BasePlugin:
    """base."""

    def __init__(self):
        """init."""
        pass

    def process(self, data):
        """process."""
        return data


class DemoPlugin(BasePlugin):
    """concrete plugin."""

    def __init__(self):
        """init."""
        super().__init__()

    def process(self, griddata):
        """Run on meb grid."""
        import meb
        return meb.checkout_griddata(griddata)
'''

PLUGIN_ANNOTATED = '''
"""带注解的插件：参数名毫无提示，只能靠注解判定。"""

from typing import Union

import numpy as np
import xarray as xr


class BasePlugin:
    """base."""

    def process(self, data):
        """process."""
        return data


class AnnotatedPlugin(BasePlugin):
    """concrete."""

    def process(
        self,
        temperature_data: Union[xr.DataArray, np.ndarray],
    ) -> Union[xr.DataArray, np.ndarray]:
        """算体感温度。"""
        if isinstance(temperature_data, xr.DataArray):
            return temperature_data * 1.0
        return np.asarray(temperature_data)
'''

PLUGIN_STATION = '''
"""站点数据插件。"""

import pandas as pd


class BasePlugin:
    """base."""

    def process(self, data):
        """process."""
        return data


class StationPlugin(BasePlugin):
    """concrete."""

    def process(self, sta: pd.DataFrame) -> pd.DataFrame:
        """按站点固定列取值。"""
        return sta[["level", "time", "dtime", "id", "lat", "lon", "data0"]]
'''

GRID_HELPER = '''
"""包内 utils：构造标准六维网格，带必备 attrs。"""

import xarray as xr


def rebuild(values, coords):
    """还原成 meb 网格。"""
    arr = xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords=coords,
    )
    arr.attrs["units"] = "degC"
    arr.attrs["model"] = "demo"
    arr.attrs["dtime_units"] = "hour"
    arr.attrs["level_type"] = "surface"
    arr.attrs["time_type"] = "BT"
    arr.attrs["time_bounds"] = [0, 0]
    return arr
'''

PLUGIN_PLAIN = '''
"""与气象数据无关的插件。"""


class BasePlugin:
    """base."""

    def process(self, data):
        """process."""
        return data


class PlainPlugin(BasePlugin):
    """concrete."""

    def process(self, values: list) -> int:
        """求和。"""
        return sum(values)
'''

PLUGIN_NO_DOC = '''
class BasePlugin:
    def __init__(self):
        pass
    def process(self, data):
        return data

class DemoPlugin(BasePlugin):
    def __init__(self):
        pass
    def process(self, data):
        return data + 1
'''


class LocalReviewTests(unittest.TestCase):
    def test_parse_mid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _mid_tree(root)
            pkg = parse_package_path(root, root / "00temp" / "demo")
            self.assertIsNotNone(pkg)
            assert pkg is not None
            self.assertEqual(pkg.layout, "mid")

    def test_structure_empty_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _mid_tree(root)
            pkg = parse_package_path(root, root / "00temp" / "demo")
            assert pkg is not None
            sec = check_structure(root, pkg)
            self.assertTrue(any(f.rule_id == "EMPTY_REQUIRED_DIR" for f in sec.findings))

    def test_plugin_and_meb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_OK, encoding="utf-8")
            # 填一点实质内容避免 EMPTY
            (base / "docs" / "README.md").write_text("# demo\n", encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            plug = check_plugins(root, pkg)
            self.assertFalse(any(f.rule_id == "NO_CONCRETE_PLUGIN" for f in plug.findings))
            meb = check_meb_grid(root, pkg, required=True)
            self.assertTrue(
                any(f.rule_id == "MEB_GRID_SIGNAL_OK" for f in meb.findings)
            )

    def test_meb_grid_from_annotation(self) -> None:
        """参数名无提示时，`xr.DataArray` 注解足以判定为网格。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(
                PLUGIN_ANNOTATED, encoding="utf-8"
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_meb_grid(root, pkg, required=True)
            self.assertEqual(sec.metrics["io_kind"], "meb")
            self.assertEqual(sec.metrics["name_hints"], [])
            self.assertEqual(sec.metrics["grid_annotations"], ["DataArray"])
            # Union 里还有 np.ndarray：并非强制 meb 格式，要单独点出来
            self.assertTrue(
                any(f.rule_id == "MEB_GRID_OPTIONAL_INPUT" for f in sec.findings)
            )
            self.assertFalse(
                any(f.rule_id == "MEB_GRID_PROCESS_UNCLEAR" for f in sec.findings)
            )

    def test_meb_station_data(self) -> None:
        """站点表也算 meb 数据格式；网格/站点只作附注。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_STATION, encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_meb_grid(root, pkg, required=True)
            self.assertEqual(sec.metrics["io_kind"], "meb")
            self.assertEqual(sec.metrics["station_column_hits"], "6/6")
            self.assertEqual(sec.metrics["shape_hint"], "站点表")

    def test_meb_grid_fingerprint_outside_src(self) -> None:
        """网格构造写在包内 utils 时，时空坐标指纹也该采信。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_PLAIN, encoding="utf-8")
            utils = base / "utils"
            utils.mkdir(exist_ok=True)
            (utils / "grid.py").write_text(GRID_HELPER, encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_meb_grid(root, pkg, required=True)
            self.assertEqual(sec.metrics["io_kind"], "meb")
            self.assertEqual(sec.metrics["grid_dim_hits"], "6/6")
            self.assertEqual(sec.metrics["grid_attr_hits"], "6/6")
            self.assertTrue(sec.metrics["evidence_outside_src"])
            # 但 process 自身仍看不出格式，要提醒复核
            self.assertTrue(
                any(f.rule_id == "MEB_GRID_PROCESS_UNCLEAR" for f in sec.findings)
            )

    def test_llm_config_found_in_package_dir(self) -> None:
        """LLM 配置只在 local_review/ 下自动查找，仓库根不再扫。"""
        from local_review import llm_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg_dir = root / "pkgdir"
            pkg_dir.mkdir()
            (pkg_dir / "local_review.llm.toml").write_text(
                'api_key = "sk-pkg"\nmodel = "m-pkg"\n', encoding="utf-8"
            )
            # 仓库根也放一份，应被忽略
            (root / "local_review.llm.toml").write_text(
                'api_key = "sk-root"\n', encoding="utf-8"
            )
            with mock.patch.object(llm_config, "PACKAGE_CONFIG_DIR", pkg_dir), \
                    mock.patch.dict("os.environ", {}, clear=True):
                cfg = llm_config.resolve_llm_config(root)
            self.assertEqual(cfg["api_key"], "sk-pkg")
            self.assertEqual(cfg["model"], "m-pkg")

    def test_llm_config_explicit_path_wins(self) -> None:
        """--llm-config 指定的路径优先，且相对路径按 --root 解析。"""
        from local_review import llm_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg_dir = root / "pkgdir"
            pkg_dir.mkdir()
            (pkg_dir / "local_review.llm.toml").write_text(
                'api_key = "sk-pkg"\n', encoding="utf-8"
            )
            (root / "mine.toml").write_text('api_key = "sk-mine"\n', encoding="utf-8")
            with mock.patch.object(llm_config, "PACKAGE_CONFIG_DIR", pkg_dir), \
                    mock.patch.dict("os.environ", {}, clear=True):
                cfg = llm_config.resolve_llm_config(root, config_path=Path("mine.toml"))
            self.assertEqual(cfg["api_key"], "sk-mine")

    def test_report_flake8_grouped_and_paths_relative(self) -> None:
        """flake8 按文件+错误码合并，路径相对包根显示。"""
        from local_review.models import Finding, SectionResult

        pkg_id = "00temp/demo"
        sec = SectionResult(name="flake8")
        for line in (98, 99, 102):
            sec.findings.append(
                Finding(
                    rule_id="FLAKE8",
                    severity="warning",
                    path=f"{pkg_id}/cli/run.py",
                    line=line,
                    message="E262 inline comment should start with '# '",
                )
            )
        sec.findings.append(
            Finding(
                rule_id="FLAKE8",
                severity="warning",
                path=f"{pkg_id}/src/__init__.py",
                line=6,
                message="W391 blank line at end of file",
            )
        )
        report = ReviewReport(package_id=pkg_id, sections=[sec])
        report.llm = {"skipped": True, "skip_reason": "dry-run"}
        md = render_markdown(report)

        self.assertIn("`cli/run.py` — E262 inline comment should start with '# '", md)
        self.assertIn("×3（行 98、99、102）", md)
        self.assertIn("`src/__init__.py` — W391 blank line at end of file（行 6）", md)
        # 单条不加计数后缀
        self.assertNotIn("W391 blank line at end of file ×1", md)
        # 包前缀不再出现在条目里
        self.assertNotIn(f"`{pkg_id}/cli/run.py", md)

    def test_report_package_level_path_reads_as_whole(self) -> None:
        """指向整包的发现不再重复包路径。"""
        from local_review.models import Finding, SectionResult

        pkg_id = "00temp/demo"
        sec = SectionResult(name="dependencies")
        sec.findings.append(
            Finding(
                rule_id="DEP_NO_MANIFEST",
                severity="warning",
                path=pkg_id,
                message="未找到任何依赖清单",
            )
        )
        report = ReviewReport(package_id=pkg_id, sections=[sec])
        report.llm = {"skipped": True, "skip_reason": "dry-run"}
        md = render_markdown(report)
        self.assertIn("`整包` — 未找到任何依赖清单", md)

    def test_report_renders_meb_verdict(self) -> None:
        """LLM 的 meb_verdict 单独成节，并在总评占一行。"""
        report = ReviewReport(package_id="00temp/demo")
        report.llm = {
            "skipped": False,
            "model": "demo-model",
            "risk_level": "medium",
            "overview": "总评。",
            "meb_verdict": {
                "verdict": "partial",
                "input": "入参为六维 DataArray",
                "output": "返回裸 ndarray，未还原成网格",
                "issues": ["出参未还原成 meb 网格"],
                "basis": "src/algo.py:120",
            },
        }
        md = render_markdown(report)
        self.assertIn("| meb 格式 | 部分符合，1 处问题 |", md)
        self.assertIn("### meb 数据格式（LLM 复核）", md)
        self.assertIn("出参未还原成 meb 网格", md)
        self.assertIn("src/algo.py:120", md)

    def test_report_flags_missing_meb_verdict(self) -> None:
        """必填字段缺失时要显式写出缺口，不静默跳过。"""
        report = ReviewReport(package_id="00temp/demo")
        report.llm = {"skipped": False, "model": "demo-model", "overview": "总评。"}
        md = render_markdown(report)
        self.assertIn("| meb 格式 | LLM 未给出判定 |", md)
        self.assertIn("_LLM 未按要求给出 meb 判定", md)

    def test_report_skips_meb_verdict_when_llm_skipped(self) -> None:
        """未调用 LLM 时不该出现这一节。"""
        report = ReviewReport(package_id="00temp/demo")
        report.llm = {"skipped": True, "skip_reason": "dry-run"}
        md = render_markdown(report)
        self.assertNotIn("meb 数据格式（LLM 复核）", md)

    def test_meb_no_signal_at_all(self) -> None:
        """毫无 meb 信号时仍报警告，避免指纹放宽后漏判。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_PLAIN, encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_meb_grid(root, pkg, required=True)
            self.assertEqual(sec.metrics["io_kind"], "unknown")
            self.assertTrue(
                any(f.rule_id == "MEB_GRID_NOT_USED" for f in sec.findings)
            )

    def test_docstring_missing_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_NO_DOC, encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_docstrings(root, pkg)
            self.assertTrue(any(f.rule_id == "DOCSTRING_MISSING" for f in sec.findings))
            self.assertGreater(sec.metrics["missing_docstring"], 0)
            self.assertFalse(
                any(f.rule_id == "DOCSTRING_COVERAGE_LOW" for f in sec.findings)
            )

    def test_dependencies_undeclared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text(
                "import os\n"
                "import numpy as np\n"
                "from pandas import DataFrame\n"
                "from .helper import util\n",
                encoding="utf-8",
            )
            (base / "test" / "test_algo.py").write_text(
                "import pytest\nimport requests\n", encoding="utf-8"
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertEqual(
                sec.metrics["undeclared"], ["numpy", "pandas", "requests"]
            )
            # stdlib 与包内相对导入不算依赖；test 里的 pytest 不要求声明
            self.assertNotIn("os", sec.metrics["third_party_imports"])
            self.assertNotIn("helper", sec.metrics["third_party_imports"])
            self.assertTrue(
                any(f.rule_id == "DEP_NO_MANIFEST" for f in sec.findings)
            )
            sev = {
                f.message.split("`")[1]: f.severity
                for f in sec.findings
                if f.rule_id == "DEP_UNDECLARED"
            }
            self.assertEqual(sev["numpy"], "warning")
            self.assertEqual(sev["requests"], "info")  # 仅测试用到

    def test_dependencies_declared_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text(
                "import numpy\nimport yaml\nimport netCDF4\n", encoding="utf-8"
            )
            (base / "requirements.txt").write_text(
                "# deps\nnumpy>=1.24\nPyYAML\nnetCDF4==1.7.2\nrich\n",
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            # 包名与 import 名不一致（PyYAML→yaml）也应认得
            self.assertEqual(sec.metrics["undeclared"], [])
            self.assertEqual(sec.metrics["unused_declared"], ["rich"])
            self.assertTrue(
                any(f.rule_id == "DEP_UNUSED_DECLARED" for f in sec.findings)
            )
            # 只有 requirements.txt 时无处可写 Python 版本，只记 info 不算警告
            no_py = [f for f in sec.findings if f.rule_id == "DEP_NO_PYTHON_VERSION"]
            self.assertEqual(len(no_py), 1)
            self.assertEqual(no_py[0].severity, "info")

    def test_dependencies_cross_file_conflict(self) -> None:
        """同一个包在两个清单里钉不同版本 → 阻断。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            (base / "requirements.txt").write_text("numpy==1.24.0\n", encoding="utf-8")
            (base / "pyproject.toml").write_text(
                '[project]\nname = "algo"\nrequires-python = ">=3.10"\n'
                'dependencies = ["numpy==2.0.0"]\n',
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            conflict = [f for f in sec.findings if f.rule_id == "DEP_VERSION_CONFLICT"]
            self.assertTrue(conflict)
            self.assertEqual(conflict[0].severity, "blocker")
            self.assertIn("numpy", conflict[0].message)
            # pyproject 提供了 requires-python，不应再报缺版本声明
            self.assertFalse(
                any(f.rule_id == "DEP_NO_PYTHON_VERSION" for f in sec.findings)
            )
            self.assertEqual(sec.metrics["python_requires"], [">=3.10"])

    def test_dependencies_marker_split_not_conflict(self) -> None:
        """按 Python 版本二选一的两个钉版本不是冲突。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            (base / "requirements.txt").write_text(
                'numpy==1.26.0; python_version < "3.10"\n'
                'numpy==2.0.0; python_version >= "3.10"\n',
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertEqual(sec.metrics["conflicts"], [])
            self.assertFalse(
                any(f.rule_id == "DEP_VERSION_CONFLICT" for f in sec.findings)
            )
            # 标记互斥只记进 metrics 供排查，不占报告条目
            self.assertTrue(sec.metrics["marker_splits"])
            self.assertFalse(
                any(f.rule_id == "DEP_MARKER_SPLIT" for f in sec.findings)
            )
            # 条件依赖本就该分开写，不该再提示「只保留一处」
            self.assertFalse(
                any(f.rule_id == "DEP_DUPLICATE_DECLARED" for f in sec.findings)
            )

    def test_dependencies_overlapping_markers_still_conflict(self) -> None:
        """标记有交集（win32 且 3.10+）时仍应判冲突。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            (base / "requirements.txt").write_text(
                'numpy==1.26.0; sys_platform == "win32"\n'
                'numpy==2.0.0; python_version >= "3.10"\n',
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            conflict = [f for f in sec.findings if f.rule_id == "DEP_VERSION_CONFLICT"]
            self.assertTrue(conflict)
            self.assertIn("环境标记", conflict[0].message)

    def test_dependencies_bound_conflict_and_flags(self) -> None:
        """下界高于上界 → 阻断；停维护/重量级/总数等标记。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text(
                "import numpy\nimport torch\nfrom mpl_toolkits import basemap\n",
                encoding="utf-8",
            )
            (base / "requirements.txt").write_text(
                "numpy>=2.0,<1.26\nbasemap\ntorch\n", encoding="utf-8"
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            rules = {f.rule_id for f in sec.findings}
            self.assertIn("DEP_VERSION_CONFLICT", rules)
            self.assertIn("DEP_DEPRECATED", rules)
            self.assertIn("DEP_HEAVY", rules)

    def test_dependencies_environment_yml_and_setup_py(self) -> None:
        """conda 清单与 setup.py 都要能解析（含 conda 包名映射）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text(
                "import torch\nimport cv2\nimport click\n", encoding="utf-8"
            )
            (base / "environment.yml").write_text(
                "name: algo\n"
                "dependencies:\n"
                "  - python=3.11\n"
                "  - pytorch=2.1\n"
                "  - opencv\n"
                "  - pip:\n"
                "    - click>=8.0\n",
                encoding="utf-8",
            )
            (base / "setup.py").write_text(
                "from setuptools import setup\n"
                "setup(name='algo', python_requires='>=3.10',"
                " install_requires=['click>=8.0'])\n",
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            # pytorch→torch、opencv→cv2 的映射生效，click 在两处声明
            self.assertEqual(sec.metrics["undeclared"], [])
            self.assertIn("3.11", " ".join(sec.metrics["python_requires"]))
            self.assertTrue(
                any(f.rule_id == "DEP_DUPLICATE_DECLARED" for f in sec.findings)
            )

    def test_dependencies_unparsed_manifest_softens_undeclared(self) -> None:
        """清单没解析出来时，未声明只能算疑似，降为 info 并注明。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            # install_requires 由函数返回，AST 字面量解析读不出来
            (base / "setup.py").write_text(
                "from setuptools import setup\n"
                "\n"
                "def _deps():\n"
                "    return ['numpy>=1.24']\n"
                "\n"
                "setup(name='algo', python_requires='>=3.10',"
                " install_requires=_deps())\n",
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertTrue(
                any(f.rule_id == "DEP_MANIFEST_UNPARSED" for f in sec.findings)
            )
            self.assertTrue(sec.metrics["undeclared_uncertain"])
            undeclared = [f for f in sec.findings if f.rule_id == "DEP_UNDECLARED"]
            self.assertTrue(undeclared)
            self.assertEqual(undeclared[0].severity, "info")
            self.assertIn("可能实为已声明", undeclared[0].message)

    def test_dependencies_python_version_from_side_files(self) -> None:
        """`.python-version` / `runtime.txt` 可补 Python 版本，但不算依赖清单。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            (base / ".python-version").write_text("3.12.10\n", encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertEqual(sec.metrics["python_requires"], ["==3.12.10"])
            self.assertEqual(
                sec.metrics["python_version_files"], ["00temp/demo/.python-version"]
            )
            self.assertFalse(
                any(f.rule_id == "DEP_NO_PYTHON_VERSION" for f in sec.findings)
            )
            # 只有它时仍属「无依赖清单」
            self.assertEqual(sec.metrics["manifests"], [])
            self.assertTrue(
                any(f.rule_id == "DEP_NO_MANIFEST" for f in sec.findings)
            )

    def test_dependencies_runtime_txt_python_version(self) -> None:
        """runtime.txt 的 `python-3.11.9` 写法也要认得。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "algo.py").write_text("import numpy\n", encoding="utf-8")
            (base / "requirements.txt").write_text("numpy>=1.26\n", encoding="utf-8")
            (base / "runtime.txt").write_text("python-3.11.9\n", encoding="utf-8")
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertEqual(sec.metrics["python_requires"], ["==3.11.9"])
            self.assertFalse(
                any(f.rule_id == "DEP_NO_PYTHON_VERSION" for f in sec.findings)
            )

    def test_dependencies_repo_internal_import_not_undeclared(self) -> None:
        """引用仓库内其他包只记 info，不当成未声明的第三方库。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (root / "NIMM" / "utils").mkdir(parents=True)
            (root / "NIMM" / "utils" / "helper.py").write_text(
                "def util():\n    return 1\n", encoding="utf-8"
            )
            (base / "src" / "algo.py").write_text(
                "import numpy\nfrom NIMM.utils.helper import util\n",
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = check_dependencies(root, pkg)
            self.assertIn("NIMM", sec.metrics["repo_internal_imports"])
            self.assertNotIn("NIMM", sec.metrics["third_party_imports"])
            self.assertNotIn("NIMM", sec.metrics["undeclared"])
            self.assertEqual(sec.metrics["undeclared"], ["numpy"])
            internal = [f for f in sec.findings if f.rule_id == "DEP_REPO_INTERNAL"]
            self.assertEqual(len(internal), 1)
            self.assertEqual(internal[0].severity, "info")

    def test_exec_no_tests_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = run_execution_checks(
                root, pkg, report_md_path=root / "out.md", skip_run=False
            )
            self.assertTrue(
                any(f.rule_id in {"EXEC_NO_TESTS", "EXEC_NO_TEST_DIR"} for f in sec.findings)
            )

    def test_exec_pytest_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_OK, encoding="utf-8")
            (base / "test" / "test_smoke.py").write_text(
                "def test_ok():\n    assert 1 + 1 == 2\n",
                encoding="utf-8",
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            sec = run_execution_checks(
                root,
                pkg,
                report_md_path=root / "out.md",
                venv_dir=root / ".venv_test",
            )
            if any(f.rule_id == "EXEC_PIP_FAILED" for f in sec.findings):
                self.skipTest("当前环境无法 pip install pytest（网络/SSL）")
            self.assertTrue(any(f.rule_id == "EXEC_PYTEST_OK" for f in sec.findings))
            # 夹具 import meb，本机没有 meb 时允许出现环境类 blocker
            self.assertFalse(
                any(
                    f.severity == "blocker"
                    and f.rule_id != "EXEC_MISSING_REQUIRED_LIB"
                    for f in sec.findings
                )
            )
            self.assertEqual(sec.metrics["required_libs"]["pytest"], "present")
            # 显式指定的 venv 视为可复用缓存，不删除
            self.assertTrue(sec.metrics["venv_reused"])
            self.assertFalse(sec.metrics["venv_removed"])
            self.assertTrue((root / ".venv_test").is_dir())

    def test_exec_missing_required_lib_is_env_blocker(self) -> None:
        """本包 import 的必需库装不上时，明确记为环境问题而非算法问题。"""
        import importlib.util

        if any(
            importlib.util.find_spec(n) is not None
            for n in ("meteva_base", "meb")
        ):
            self.skipTest("本机已装 meteva_base，无法构造缺库场景")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "src" / "plugin.py").write_text(PLUGIN_OK, encoding="utf-8")
            (base / "test" / "test_smoke.py").write_text(
                "def test_ok():\n    assert True\n", encoding="utf-8"
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            with mock.patch(
                "local_review.run_check._pip_install",
                return_value=(1, "ERROR: No matching distribution found"),
            ):
                sec = run_execution_checks(root, pkg, report_md_path=root / "out.md")
            self.assertEqual(sec.metrics["required_libs"]["meteva_base"], "missing")
            miss = [f for f in sec.findings if f.rule_id == "EXEC_MISSING_REQUIRED_LIB"]
            self.assertTrue(miss)
            # 夹具写的是别名 `import meb`，也应判定为「本包用到」
            self.assertEqual(miss[0].severity, "blocker")
            self.assertIn("meteva_base", miss[0].message)

    def test_exec_temp_venv_removed(self) -> None:
        """未指定 --venv 时用临时目录，跑完（即使失败）也要删掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = _mid_tree(root)
            (base / "test" / "test_smoke.py").write_text(
                "def test_ok():\n    assert True\n", encoding="utf-8"
            )
            pkg = parse_package_path(root, base)
            assert pkg is not None
            with mock.patch(
                "local_review.run_check._pip_install",
                return_value=(1, "stub failure"),
            ):
                sec = run_execution_checks(
                    root, pkg, report_md_path=root / "out.md"
                )
            venv_dir = Path(sec.metrics["venv"])
            self.assertTrue(sec.metrics["venv_removed"])
            self.assertFalse(venv_dir.exists())
            self.assertFalse((base / ".local_review_venv").exists())


if __name__ == "__main__":
    unittest.main()
