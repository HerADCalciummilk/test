"""L1 机器审核入口。对照 rules.py，输出 review.json。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from rules import (
    CREDENTIAL_PATTERNS,
    HARDCODED_PATH_PATTERNS,
    MAX_TEXT_FILE_BYTES,
    NATIVE_SUFFIXES,
    PLUGIN_IO_PATTERNS,
    REQUIRED_PACKAGE_DIRS,
    RULES,
    SKIP_DIR_NAMES,
    SKIP_FILE_SUFFIXES,
)


@dataclass
class Finding:
    rule_id: str
    severity: str
    path: str
    line: int | None
    message: str


def repo_rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_FILE_SUFFIXES:
            continue
        yield path


def read_text(path: Path) -> str | None:
    if path.stat().st_size > MAX_TEXT_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def package_root_for(rel: Path) -> Path | None:
    parts = rel.parts
    if not parts:
        return None
    if parts[0] == "00temp" and len(parts) >= 2 and parts[1] not in SKIP_DIR_NAMES:
        return Path(parts[0]) / parts[1]
    if parts[0] == "NIMM" and len(parts) >= 3 and parts[1] not in SKIP_DIR_NAMES:
        return Path(parts[0]) / parts[1] / parts[2]
    return None


def changed_paths(repo: Path, base: str) -> list[Path]:
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
    found: set[Path] = set()
    for rel in rel_files:
        root = package_root_for(rel)
        if root is None:
            continue
        abs_root = repo / root
        if (abs_root / "src").is_dir() or (abs_root / "cli").is_dir():
            found.add(root)
    return sorted(found)


def add_finding(
    findings: list[Finding],
    rule_id: str,
    path: str,
    message: str,
    line: int | None = None,
) -> None:
    rule = RULES[rule_id]
    findings.append(
        Finding(
            rule_id=rule.id,
            severity=rule.severity,
            path=path,
            line=line,
            message=message,
        )
    )


def check_structure(repo: Path, package: Path, findings: list[Finding]) -> None:
    official = package.parts[0] == "NIMM"
    rule_id = "MISSING_REQUIRED_DIR_OFFICIAL" if official else "MISSING_REQUIRED_DIR"
    missing = [name for name in REQUIRED_PACKAGE_DIRS if not (repo / package / name).is_dir()]
    if missing:
        add_finding(
            findings,
            rule_id,
            package.as_posix(),
            f"缺少必要目录: {', '.join(missing)}",
        )


def check_file_content(repo: Path, path: Path, findings: list[Finding]) -> None:
    rel = repo_rel(repo, path)
    text = read_text(path)
    if text is None:
        return

    for index, line in enumerate(text.splitlines(), start=1):
        for pattern in CREDENTIAL_PATTERNS:
            if re.search(pattern, line):
                add_finding(findings, "CREDENTIAL_PATTERN", rel, "匹配到疑似凭据或私钥", index)
                break
        for pattern in HARDCODED_PATH_PATTERNS:
            if re.search(pattern, line):
                add_finding(findings, "HARDCODED_BIZ_PATH", rel, line.strip()[:200], index)
                break

    if "src" in path.parts and path.suffix == ".py":
        for index, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            for pattern in PLUGIN_IO_PATTERNS:
                if re.search(pattern, line):
                    add_finding(findings, "PLUGIN_FILE_IO", rel, line.strip()[:200], index)
                    break


def check_native_binaries(repo: Path, package: Path, findings: list[Finding]) -> None:
    docs_text = ""
    docs_dir = repo / package / "docs"
    if docs_dir.is_dir():
        for doc in docs_dir.rglob("*"):
            if doc.is_file() and doc.suffix.lower() in {".md", ".txt", ".rst"}:
                piece = read_text(doc)
                if piece:
                    docs_text += piece
    for path in iter_files(repo / package):
        if path.suffix.lower() not in NATIVE_SUFFIXES:
            continue
        rel = repo_rel(repo, path)
        if path.name.lower() not in docs_text.lower() and path.suffix.lower() not in docs_text.lower():
            add_finding(findings, "UNDECLARED_NATIVE_BINARY", rel, "docs 中未说明该二进制扩展")


def run_flake8(repo: Path, py_files: list[Path], findings: list[Finding]) -> None:
    if not py_files:
        return
    rel_files = [repo_rel(repo, path) for path in py_files]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flake8",
            "--max-line-length=120",
            "--format=%(path)s:%(row)d:%(text)s",
            *rel_files,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if "No module named" in (result.stderr or ""):
        return
    line_re = re.compile(r"^(.*):(\d+):(.*)$")
    for raw in result.stdout.splitlines():
        match = line_re.match(raw.replace("\\", "/"))
        if match is None:
            continue
        add_finding(findings, "FLAKE8", match.group(1), match.group(3).strip(), int(match.group(2)))


def github_annotate(findings: list[Finding]) -> None:
    for item in findings:
        kind = "error" if item.severity == "blocker" else "warning"
        line = item.line or 1
        print(f"::{kind} file={item.path},line={line}::{item.rule_id}: {item.message}")


def build_report(packages: list[str], findings: list[Finding]) -> dict:
    blockers = [asdict(item) for item in findings if item.severity == "blocker"]
    warnings = [asdict(item) for item in findings if item.severity == "warning"]
    return {
        "gate": "l1",
        "packages": packages,
        "summary": {
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NIMM L1 算法审核")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--base", default="", help="git diff 的基准 commit / ref")
    parser.add_argument("--path", action="append", default=[], help="直接指定算法包相对路径，可重复")
    parser.add_argument("--json", default="review.json", help="报告输出路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()

    findings: list[Finding] = []
    packages: list[Path] = []

    if args.path:
        packages = [Path(item) for item in args.path]
    elif args.base:
        packages = discover_packages(repo, changed_paths(repo, args.base))
    else:
        packages = []

    scan_files: list[Path] = []
    if args.path or args.base:
        if packages:
            for package in packages:
                check_structure(repo, package, findings)
                check_native_binaries(repo, package, findings)
                for path in iter_files(repo / package):
                    scan_files.append(path)
                    check_file_content(repo, path, findings)
        elif args.base:
            for rel in changed_paths(repo, args.base):
                abs_path = repo / rel
                if abs_path.is_file():
                    scan_files.append(abs_path)
                    check_file_content(repo, abs_path, findings)

    py_files = []
    for path in scan_files:
        abs_path = path if path.is_absolute() else repo / path
        if abs_path.is_file() and abs_path.suffix == ".py":
            py_files.append(abs_path)
    run_flake8(repo, py_files, findings)

    report = build_report([item.as_posix() for item in packages], findings)
    out = Path(args.json)
    if not out.is_absolute():
        out = repo / out
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    github_annotate(findings)
    print(
        f"L1 完成：packages={report['packages'] or '无'} "
        f"blockers={report['summary']['blocker_count']} "
        f"warnings={report['summary']['warning_count']} "
        f"report={out}"
    )
    return 1 if report["summary"]["blocker_count"] else 0


if __name__ == "__main__":
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    raise SystemExit(main())
