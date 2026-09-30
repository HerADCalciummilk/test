"""注释检查：公开 API 必须有 docstring，缺失即逐条记录（不做覆盖率阈值）。"""

from __future__ import annotations

import ast
from pathlib import Path

from .config import DOCSTRING_MISSING_LIST_LIMIT, SKIP_DIR_NAMES
from .models import Finding, SectionResult
from .package import PackageRef, read_text, repo_rel


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _doc_ok(node: ast.AST) -> bool:
    return bool(ast.get_docstring(node))


def check_docstrings(root: Path, package: PackageRef) -> SectionResult:
    """列出源码根下所有缺 docstring 的公开模块/类/方法/函数。"""
    section = SectionResult(name="docstrings")
    src = package.source_dir(root)
    if not src.is_dir():
        section.skipped = True
        section.skip_reason = "源码根不存在"
        return section

    total = 0
    miss_paths: list[tuple[str, int, str]] = []

    for path in src.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        rel = repo_rel(root, path)

        # 模块 docstring：非 __init__ 或 __init__ 有实质内容时计
        if path.name != "__init__.py" or tree.body:
            total += 1
            if not _doc_ok(tree):
                miss_paths.append((rel, 1, "module"))

        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _is_public(node.name):
                total += 1
                if not _doc_ok(node):
                    miss_paths.append((f"{rel}:{node.name}", node.lineno, "class"))
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not _is_public(item.name):
                            continue
                        # 其它 dunder 不强制；__init__ 计入
                        if item.name.startswith("__") and item.name.endswith("__"):
                            if item.name != "__init__":
                                continue
                        total += 1
                        if not _doc_ok(item):
                            miss_paths.append(
                                (f"{rel}:{node.name}.{item.name}", item.lineno, "method")
                            )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not _is_public(node.name):
                    continue
                if node.name.startswith("__") and node.name.endswith("__"):
                    continue
                total += 1
                if not _doc_ok(node):
                    miss_paths.append((f"{rel}:{node.name}", node.lineno, "function"))

    section.metrics = {
        "public_api_total": total,
        "missing_docstring": len(miss_paths),
    }

    for path_id, lineno, kind in miss_paths[:DOCSTRING_MISSING_LIST_LIMIT]:
        section.findings.append(
            Finding(
                rule_id="DOCSTRING_MISSING",
                severity="warning",
                path=path_id,
                message=f"公开 {kind} 缺少 docstring",
                line=lineno,
            )
        )
    remaining = len(miss_paths) - DOCSTRING_MISSING_LIST_LIMIT
    if remaining > 0:
        section.findings.append(
            Finding(
                rule_id="DOCSTRING_MISSING",
                severity="info",
                path=package.package_id,
                message=f"另有 {remaining} 处缺 docstring 未逐条列出",
            )
        )

    return section
