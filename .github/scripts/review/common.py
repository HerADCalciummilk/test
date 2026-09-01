"""L1/L2 共用的仓库扫描与包发现工具。

职责：路径规范化、文件遍历、git 变更列表、算法包解析（中间目录 / 正式分散树）。
不含审核规则本身（规则在 rules.py；检查在 l1_review / l2_review）。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from rules import MAX_TEXT_FILE_BYTES, SKIP_DIR_NAMES, SKIP_FILE_SUFFIXES

# 正式树：与 NIMM 同级的配套根目录名
OFFICIAL_COMPANION_TOPS = ("cli", "test", "docs", "nbs", "resource")
# NIMM 下不作为「算法种类」的公共目录
OFFICIAL_SKIP_KINDS = frozenset({"utils"})


@dataclass(frozen=True)
class PackageRef:
    """一次审核识别到的算法包（中间或正式）。"""

    layout: Literal["mid", "official"]
    # 稳定 ID：00temp/<pkg> 或 NIMM/<kind>/<pkg>
    package_id: str
    # 中间：00temp/<pkg>；正式：None（用 kind/pkg）
    mid_root: Path | None = None
    kind: str | None = None
    pkg: str | None = None

    def source_dir(self, repo: Path) -> Path:
        """插件/源码扫描根。"""
        if self.layout == "mid":
            assert self.mid_root is not None
            return repo / self.mid_root / "src"
        assert self.kind and self.pkg
        return repo / "NIMM" / self.kind / self.pkg

    def docs_dir(self, repo: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            return repo / self.mid_root / "docs"
        assert self.kind and self.pkg
        return repo / "docs" / self.kind / self.pkg

    def cli_dir(self, repo: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            return repo / self.mid_root / "cli"
        assert self.kind and self.pkg
        return repo / "cli" / self.kind / self.pkg

    def required_tree_paths(self) -> dict[str, Path]:
        """结构门禁用的逻辑名 → 相对仓库路径。"""
        if self.layout == "mid":
            assert self.mid_root is not None
            return {name: self.mid_root / name for name in (
                "src", "cli", "test", "docs", "nbs", "resource"
            )}
        assert self.kind and self.pkg
        paths = {"NIMM": Path("NIMM") / self.kind / self.pkg}
        for top in OFFICIAL_COMPANION_TOPS:
            paths[top] = Path(top) / self.kind / self.pkg
        return paths

    def iter_scan_roots(self, repo: Path) -> list[Path]:
        """整包内容扫描应覆盖的目录（已存在的）。"""
        roots: list[Path] = []
        for rel in self.required_tree_paths().values():
            abs_dir = repo / rel
            if abs_dir.is_dir():
                roots.append(abs_dir)
        return roots


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


def _mid_ref(pkg: str) -> PackageRef:
    root = Path("00temp") / pkg
    return PackageRef(layout="mid", package_id=root.as_posix(), mid_root=root)


def _official_ref(kind: str, pkg: str) -> PackageRef:
    return PackageRef(
        layout="official",
        package_id=f"NIMM/{kind}/{pkg}",
        kind=kind,
        pkg=pkg,
    )


def parse_package_ref(rel: Path) -> PackageRef | None:
    """从变更/路径解析算法包身份；无法识别则 None。"""
    parts = rel.parts
    if not parts:
        return None

    if parts[0] == "00temp" and len(parts) >= 2 and parts[1] not in SKIP_DIR_NAMES:
        return _mid_ref(parts[1])

    if parts[0] == "NIMM" and len(parts) >= 3:
        kind, pkg = parts[1], parts[2]
        if kind in SKIP_DIR_NAMES or kind in OFFICIAL_SKIP_KINDS:
            return None
        if pkg in SKIP_DIR_NAMES:
            return None
        return _official_ref(kind, pkg)

    if parts[0] in OFFICIAL_COMPANION_TOPS and len(parts) >= 3:
        kind, pkg = parts[1], parts[2]
        if kind in SKIP_DIR_NAMES or kind in OFFICIAL_SKIP_KINDS:
            return None
        if pkg in SKIP_DIR_NAMES:
            return None
        return _official_ref(kind, pkg)

    return None


def package_root_for(rel: Path) -> Path | None:
    """兼容旧接口：返回用于展示的包 ID 路径（中间为 00temp/pkg，正式为 NIMM/kind/pkg）。"""
    ref = parse_package_ref(rel)
    if ref is None:
        return None
    return Path(ref.package_id)


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


def mid_has_entry_dirs(repo: Path, ref: PackageRef) -> bool:
    """中间包：包内有 src/ 或 cli/。"""
    assert ref.layout == "mid" and ref.mid_root is not None
    root = repo / ref.mid_root
    return (root / "src").is_dir() or (root / "cli").is_dir()


def discover_packages(repo: Path, rel_files: list[Path]) -> list[PackageRef]:
    """由变更文件聚合算法包。

    - 中间：须包内有 src/ 或 cli/
    - 正式：路径命中 NIMM|cli|test|docs|nbs|resource/<kind>/<pkg> 即纳入（结构完整性另检）
    """
    found: dict[str, PackageRef] = {}
    for rel in rel_files:
        ref = parse_package_ref(rel)
        if ref is None:
            continue
        if ref.layout == "mid" and not mid_has_entry_dirs(repo, ref):
            continue
        found[ref.package_id] = ref
    return sorted(found.values(), key=lambda r: r.package_id)


def packages_missing_entry_dirs(repo: Path, rel_files: list[Path]) -> list[PackageRef]:
    """仅中间目录：路径像 00temp/<pkg> 但同时缺少 src/ 与 cli/。"""
    missing: dict[str, PackageRef] = {}
    for rel in rel_files:
        ref = parse_package_ref(rel)
        if ref is None or ref.layout != "mid":
            continue
        if mid_has_entry_dirs(repo, ref):
            continue
        missing[ref.package_id] = ref
    return sorted(missing.values(), key=lambda r: r.package_id)


def resolve_path_arg(repo: Path, raw: str) -> PackageRef | None:
    """解析 --path 参数为 PackageRef（不要求目录已存在）。"""
    parts = Path(raw).parts
    if not parts:
        return None
    if parts[0] == "00temp" and len(parts) >= 2:
        return _mid_ref(parts[1])
    if parts[0] == "NIMM" and len(parts) >= 3:
        if parts[1] in OFFICIAL_SKIP_KINDS:
            return None
        return _official_ref(parts[1], parts[2])
    if parts[0] in OFFICIAL_COMPANION_TOPS and len(parts) >= 3:
        if parts[1] in OFFICIAL_SKIP_KINDS:
            return None
        return _official_ref(parts[1], parts[2])
    return None
