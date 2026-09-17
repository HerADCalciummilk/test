"""包路径解析与文件工具（独立实现，不依赖 .github/scripts/review）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from .config import (
    MAX_TEXT_FILE_BYTES,
    OFFICIAL_COMPANION_TOPS,
    REQUIRED_MID_DIRS,
    SKIP_DIR_NAMES,
)


@dataclass(frozen=True)
class PackageRef:
    """一次本地检查识别到的算法包。"""

    layout: Literal["mid", "official"]
    package_id: str
    mid_root: Path | None = None
    kind: str | None = None
    pkg: str | None = None
    # 清单可关闭 meb 强制（非网格算法）
    meb_grid_required: bool = True

    def source_dir(self, root: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            return root / self.mid_root / "src"
        assert self.kind and self.pkg
        return root / "NIMM" / self.kind / self.pkg

    def docs_dir(self, root: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            return root / self.mid_root / "docs"
        assert self.kind and self.pkg
        return root / "docs" / self.kind / self.pkg

    def cli_dir(self, root: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            return root / self.mid_root / "cli"
        assert self.kind and self.pkg
        return root / "cli" / self.kind / self.pkg

    def test_dir(self, root: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            if self.mid_root.is_absolute():
                return self.mid_root / "test"
            return root / self.mid_root / "test"
        assert self.kind and self.pkg
        return root / "test" / self.kind / self.pkg

    def package_root(self, root: Path) -> Path:
        if self.layout == "mid":
            assert self.mid_root is not None
            if self.mid_root.is_absolute():
                return self.mid_root
            return root / self.mid_root
        assert self.kind and self.pkg
        return root / "NIMM" / self.kind / self.pkg

    def required_tree_paths(self) -> dict[str, Path]:
        if self.layout == "mid":
            assert self.mid_root is not None
            return {name: self.mid_root / name for name in REQUIRED_MID_DIRS}
        assert self.kind and self.pkg
        paths = {"NIMM": Path("NIMM") / self.kind / self.pkg}
        for top in OFFICIAL_COMPANION_TOPS:
            paths[top] = Path(top) / self.kind / self.pkg
        return paths


def repo_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        yield path


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            return None
        # utf-8-sig：Windows 上常见 BOM，否则 ast/tomllib 会误报语法错
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None


def path_is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def parse_package_path(root: Path, path: Path) -> PackageRef | None:
    """从用户给定路径解析中间包或正式包。"""
    root = root.resolve()
    path = path.resolve()
    try:
        rel = path.relative_to(root)
    except ValueError:
        # 允许直接传入包目录（不在 root 下时，以 path 自身为 mid 根）
        if path.is_dir() and (path / "src").is_dir():
            return PackageRef(
                layout="mid",
                package_id=path.name,
                mid_root=path,
            )
        return None

    parts = rel.parts
    if not parts:
        return None

    # 00temp/<pkg> 或 00temp/<pkg>/...
    if parts[0] == "00temp" and len(parts) >= 2:
        mid = Path("00temp") / parts[1]
        return PackageRef(
            layout="mid",
            package_id=mid.as_posix(),
            mid_root=mid,
        )

    # NIMM/<kind>/<pkg>
    if parts[0] == "NIMM" and len(parts) >= 3 and parts[1] != "utils":
        kind, pkg = parts[1], parts[2]
        return PackageRef(
            layout="official",
            package_id=f"NIMM/{kind}/{pkg}",
            kind=kind,
            pkg=pkg,
        )

    # cli|test|docs|nbs|resource/<kind>/<pkg>
    if parts[0] in OFFICIAL_COMPANION_TOPS and len(parts) >= 3:
        kind, pkg = parts[1], parts[2]
        return PackageRef(
            layout="official",
            package_id=f"NIMM/{kind}/{pkg}",
            kind=kind,
            pkg=pkg,
        )

    # 直接指向含 src/ 的目录（相对 root）
    abs_path = root / rel if not path.is_absolute() else path
    if abs_path.is_dir() and (abs_path / "src").is_dir():
        return PackageRef(
            layout="mid",
            package_id=rel.as_posix(),
            mid_root=rel,
        )

    return None


def _review_run_candidates(root: Path, package: PackageRef) -> list[Path]:
    candidates = [package.package_root(root) / "review_run.toml"]
    if package.layout == "mid" and package.mid_root is not None:
        if package.mid_root.is_absolute():
            candidates.append(package.mid_root / "review_run.toml")
        else:
            candidates.append(root / package.mid_root / "review_run.toml")
    # 去重且保序
    seen: set[str] = set()
    out: list[Path] = []
    for c in candidates:
        key = str(c.resolve()) if c.exists() else str(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def load_meb_required_flag(root: Path, package: PackageRef) -> bool:
    """读取可选清单 review_run.toml 中的 meb_grid_required（默认 True）。"""
    cfg = load_run_config(root, package)
    return bool(cfg.get("meb_grid_required", True))


def load_run_config(root: Path, package: PackageRef) -> dict:
    """解析包内 review_run.toml（简易 key = value）。

    动态检查仅可能用到 timeout_sec / requirements；
    meb_grid_required 供静态 meb 使用。
    """
    defaults: dict = {
        "meb_grid_required": True,
        "timeout_sec": 300,
        "requirements": "",
    }
    for cand in _review_run_candidates(root, package):
        if not cand.is_file():
            continue
        text = read_text(cand) or ""
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "meb_grid_required":
                defaults[key] = val.lower() not in {"false", "0", "no"}
            elif key == "timeout_sec":
                try:
                    defaults[key] = int(val)
                except ValueError:
                    pass
            elif key == "requirements":
                defaults[key] = val
        defaults["_config_path"] = str(cand)
        break
    return defaults
