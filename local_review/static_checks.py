"""结构、语法、插件形态、简易 flake8（独立实现）。"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import (
    PLACEHOLDER_FILE_NAMES,
    PLUGIN_BASE_NAMES,
    SKIP_DIR_NAMES,
)
from .models import Finding, SectionResult
from .package import PackageRef, iter_files, read_text, repo_rel


def _ast_base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _method_body_empty(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for stmt in fn.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr):
            value = stmt.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                continue
            if isinstance(value, ast.Constant) and value.value is Ellipsis:
                continue
        return False
    return True


def _inherits_plugin_base(
    class_name: str,
    bases_by_class: dict[str, list[str]],
    visited: set[str] | None = None,
) -> bool:
    if visited is None:
        visited = set()
    if class_name in visited:
        return False
    visited.add(class_name)
    for base in bases_by_class.get(class_name, []):
        if base in PLUGIN_BASE_NAMES:
            return True
        if _inherits_plugin_base(base, bases_by_class, visited):
            return True
    return False


@dataclass
class _ClassRecord:
    name: str
    base_names: list[str]
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
    rel: str
    lineno: int
    in_utils: bool


def _abs_required_dir(root: Path, package: PackageRef, name: str, rel: Path) -> Path:
    if package.layout == "mid" and package.mid_root is not None:
        if package.mid_root.is_absolute():
            return package.mid_root / name
        return root / package.mid_root / name
    return root / rel


def check_structure(root: Path, package: PackageRef) -> SectionResult:
    section = SectionResult(name="structure")
    for name, rel in package.required_tree_paths().items():
        abs_dir = _abs_required_dir(root, package, name, rel)
        display = (
            abs_dir.as_posix()
            if package.mid_root is not None and package.mid_root.is_absolute()
            else str(rel).replace("\\", "/")
        )

        if not abs_dir.is_dir():
            rule = (
                "MISSING_REQUIRED_DIR_OFFICIAL"
                if package.layout == "official"
                else "MISSING_REQUIRED_DIR"
            )
            section.findings.append(
                Finding(
                    rule_id=rule,
                    severity="blocker",
                    path=display,
                    message=f"缺少必要目录: {name}",
                )
            )
            continue

        entries = [p for p in abs_dir.iterdir() if p.name not in SKIP_DIR_NAMES]
        real = [
            p for p in entries
            if not (p.is_file() and p.name in PLACEHOLDER_FILE_NAMES)
        ]
        if not real:
            section.findings.append(
                Finding(
                    rule_id="EMPTY_REQUIRED_DIR",
                    severity="warning",
                    path=display,
                    message=f"目录无实质内容: {name}",
                )
            )
    return section


def check_python_syntax(root: Path, package: PackageRef) -> SectionResult:
    section = SectionResult(name="syntax")
    src = package.source_dir(root)
    roots = [src, package.cli_dir(root)]
    for base in roots:
        if not base.is_dir():
            continue
        for path in iter_files(base):
            if path.suffix != ".py":
                continue
            text = read_text(path)
            if text is None:
                continue
            try:
                ast.parse(text, filename=str(path))
            except SyntaxError as exc:
                section.findings.append(
                    Finding(
                        rule_id="PYTHON_SYNTAX_ERROR",
                        severity="blocker",
                        path=repo_rel(root, path),
                        message=exc.msg or "Python 语法错误",
                        line=exc.lineno,
                    )
                )
    return section


def check_plugins(root: Path, package: PackageRef) -> SectionResult:
    section = SectionResult(name="plugins")
    src = package.source_dir(root)
    if not src.is_dir():
        section.findings.append(
            Finding(
                rule_id="NO_CONCRETE_PLUGIN",
                severity="blocker",
                path=repo_rel(root, src),
                message="源码根不存在，无法检查插件",
            )
        )
        return section

    records: list[_ClassRecord] = []
    for path in src.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            rel_to_src = path.relative_to(src)
        except ValueError:
            continue
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        in_utils = "utils" in rel_to_src.parts
        rel = repo_rel(root, path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = [n for n in (_ast_base_name(b) for b in node.bases) if n]
            methods = {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            records.append(
                _ClassRecord(
                    name=node.name,
                    base_names=base_names,
                    methods=methods,
                    rel=rel,
                    lineno=node.lineno,
                    in_utils=in_utils,
                )
            )

    bases_by_class = {rec.name: rec.base_names for rec in records}
    concrete = 0
    for rec in records:
        if rec.in_utils or rec.name in PLUGIN_BASE_NAMES:
            continue
        if not _inherits_plugin_base(rec.name, bases_by_class):
            continue
        concrete += 1
        loc = f"{rec.rel}:{rec.name}"
        if "__init__" not in rec.methods:
            section.findings.append(
                Finding(
                    rule_id="PLUGIN_MISSING_INIT",
                    severity="blocker",
                    path=loc,
                    message="具体插件类缺少 __init__",
                    line=rec.lineno,
                )
            )
        process_fn = rec.methods.get("process")
        if process_fn is None:
            section.findings.append(
                Finding(
                    rule_id="PLUGIN_MISSING_PROCESS",
                    severity="blocker",
                    path=loc,
                    message="具体插件类缺少 process",
                    line=rec.lineno,
                )
            )
        elif _method_body_empty(process_fn):
            section.findings.append(
                Finding(
                    rule_id="PLUGIN_EMPTY_PROCESS",
                    severity="blocker",
                    path=loc,
                    message="process 为空实现",
                    line=process_fn.lineno,
                )
            )

    if concrete == 0:
        section.findings.append(
            Finding(
                rule_id="NO_CONCRETE_PLUGIN",
                severity="blocker",
                path=repo_rel(root, src),
                message="源码根中未找到继承 BasePlugin/PostProcessingPlugin 的具体插件类（已跳过 utils/）",
            )
        )
    section.metrics["concrete_plugin_count"] = concrete
    return section


def check_flake8(root: Path, package: PackageRef) -> SectionResult:
    section = SectionResult(name="flake8")
    targets: list[str] = []
    for d in (package.source_dir(root), package.cli_dir(root)):
        if d.is_dir():
            targets.append(str(d))
    if not targets:
        section.skipped = True
        section.skip_reason = "无源码/cli 目录"
        return section

    cmd = [
        sys.executable, "-m", "flake8",
        "--max-line-length=120",
        "--extend-ignore=E203",
        *targets,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        section.skipped = True
        section.skip_reason = f"无法运行 flake8: {exc}"
        return section

    # path:line:col: code message
    line_re = re.compile(r"^(.*?):(\d+):\d+:\s*(\w+)\s+(.*)$")
    for line in (proc.stdout or "").splitlines():
        m = line_re.match(line.strip())
        if not m:
            continue
        fpath, lineno, code, msg = m.groups()
        try:
            rel = repo_rel(root, Path(fpath))
        except Exception:
            rel = fpath
        section.findings.append(
            Finding(
                rule_id="FLAKE8",
                severity="warning",
                path=rel,
                message=f"{code} {msg}",
                line=int(lineno),
            )
        )
    return section


def run_static_checks(root: Path, package: PackageRef) -> list[SectionResult]:
    return [
        check_structure(root, package),
        check_python_syntax(root, package),
        check_plugins(root, package),
        check_flake8(root, package),
    ]
