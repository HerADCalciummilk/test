"""L1/L2 共用的仓库扫描与包发现工具。

职责：路径规范化、文件遍历、git 变更列表、算法包根解析。
不含审核规则本身（规则在 rules.py；检查在 l1_review / l2_review）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Iterable

from rules import MAX_TEXT_FILE_BYTES, SKIP_DIR_NAMES, SKIP_FILE_SUFFIXES


def repo_rel(root: Path, path: Path) -> str:
    """把绝对路径收成仓库内 posix 相对路径，便于报告跨平台一致。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(root: Path) -> Iterable[Path]:
    """递归列出待扫描文件，跳过缓存目录与大体积数据后缀。"""
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_FILE_SUFFIXES:
            continue
        yield path


def read_text(path: Path) -> str | None:
    """读取 UTF-8 文本；超大或非文本则返回 None（跳过内容规则）。"""
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def package_root_for(rel: Path) -> Path | None:
    """从变更文件相对路径解析算法包根。

    - 00temp/<pkg>/...           → 00temp/<pkg>
    - NIMM/<kind>/<pkg>/...      → NIMM/<kind>/<pkg>
    其它路径返回 None。
    """
    parts = rel.parts
    if not parts:
        return None
    if parts[0] == "00temp" and len(parts) >= 2 and parts[1] not in SKIP_DIR_NAMES:
        return Path(parts[0]) / parts[1]
    if parts[0] == "NIMM" and len(parts) >= 3 and parts[1] not in SKIP_DIR_NAMES:
        return Path(parts[0]) / parts[1] / parts[2]
    return None


def changed_paths(repo: Path, base: str) -> list[Path]:
    """相对 base 的变更文件列表（Added/Copied/Modified/Renamed）。"""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "git diff 失败", file=sys.stderr)
        return []
    paths = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            paths.append(Path(line))
    return paths


def discover_packages(repo: Path, rel_files: list[Path]) -> list[Path]:
    """由变更文件聚合出算法包；包根下需有 src/ 或 cli/。"""
    found: set[Path] = set()
    for rel in rel_files:
        root = package_root_for(rel)
        if root is None:
            continue
        abs_root = repo / root
        if (abs_root / "src").is_dir() or (abs_root / "cli").is_dir():
            found.add(root)
    return sorted(found)


def packages_missing_entry_dirs(repo: Path, rel_files: list[Path]) -> list[Path]:
    """变更落在算法路径形态下，但包根同时缺少 src/ 与 cli/ 的候选根。

    此类路径不进入 discover_packages，整包检查会跳过；调用方应记 PACKAGE_NO_ENTRY_DIR（blocker）。
    """
    missing: set[Path] = set()
    for rel in rel_files:
        root = package_root_for(rel)
        if root is None:
            continue
        abs_root = repo / root
        if (abs_root / "src").is_dir() or (abs_root / "cli").is_dir():
            continue
        missing.add(root)
    return sorted(missing)
