"""L1 机器审核入口（本目录三件套之一：检查）。

职责：根据 git 变更或 --path 定位算法包，对照 rules.py 执行检查，写出 review.json，
并在 Actions 日志中输出 ::error / ::warning 注解。

典型调用：
  # PR / CI：相对基线扫描变更涉及的包
  python review.py --base <base_sha> --json review.json
  # 本地自检：直接指定包
  python review.py --path 00temp/demo_algo_clean --json review.json

退出码：存在 blocker 时返回 1，否则 0（workflow 据此决定是否红灯）。
"""

from __future__ import annotations

import argparse
import ast
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
    PLUGIN_BASE_NAMES,
    PLUGIN_IO_PATTERNS,
    PLUGIN_SKIP_SRC_DIR_NAMES,
    REQUIRED_PACKAGE_DIRS,
    RULES,
    SKIP_DIR_NAMES,
    SKIP_FILE_SUFFIXES,
)


@dataclass
class Finding:
    """单条检查发现；severity 来自 RULES[rule_id]。"""

    rule_id: str
    severity: str
    path: str
    line: int | None
    message: str


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


def add_finding(
    findings: list[Finding],
    rule_id: str,
    path: str,
    message: str,
    line: int | None = None,
) -> None:
    """按 RULES 填 severity，追加一条 Finding。"""
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
    """必要目录是否齐全；正式树与中间目录使用不同 rule_id，均为 blocker。"""
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
    """逐行内容规则：凭据、硬编码业务路径；src 下额外查疑似文件 I/O。"""
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
    """包内 .so/.pyd/.dll 须在 docs 中有所说明。"""
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


def _ast_base_name(node: ast.expr) -> str | None:
    """从 AST 基类表达式取出简单类名（Name 或 Attribute.attr）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _method_body_empty(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """仅 docstring / pass / ... 视为空实现（禁止用空 process 凑检）。"""
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


def check_plugins(repo: Path, package: Path, findings: list[Finding]) -> None:
    """插件形态检查（AST）。

    - 扫描 src/（跳过 utils）
    - 基类名 BasePlugin / PostProcessingPlugin 本身不要求业务 process
    - 继承二者的具体类：须有 __init__、非空 process
    - 包内至少一个具体插件；PostProcessingPlugin 定义时建议直接继承 BasePlugin
    """
    src = repo / package / "src"
    if not src.is_dir():
        return

    concrete_count = 0
    for path in src.rglob("*.py"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            rel_to_src = path.relative_to(src)
        except ValueError:
            continue
        if any(part in PLUGIN_SKIP_SRC_DIR_NAMES for part in rel_to_src.parts):
            continue

        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        rel = repo_rel(repo, path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            base_names = [name for name in (_ast_base_name(b) for b in node.bases) if name]

            # 中间基类应挂在 BasePlugin 下（仅检查直接基类名）
            if node.name == "PostProcessingPlugin" and "BasePlugin" not in base_names:
                add_finding(
                    findings,
                    "PLUGIN_BASE_CHAIN",
                    rel,
                    "PostProcessingPlugin 未直接继承 BasePlugin",
                    node.lineno,
                )

            # 跳过基类定义本身
            if node.name in PLUGIN_BASE_NAMES:
                continue
            if not any(name in PLUGIN_BASE_NAMES for name in base_names):
                continue

            concrete_count += 1
            methods = {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            class_loc = f"{rel}:{node.name}"

            if "__init__" not in methods:
                add_finding(
                    findings,
                    "PLUGIN_MISSING_INIT",
                    class_loc,
                    "具体插件类缺少 __init__",
                    node.lineno,
                )

            process_fn = methods.get("process")
            if process_fn is None:
                add_finding(
                    findings,
                    "PLUGIN_MISSING_PROCESS",
                    class_loc,
                    "具体插件类缺少 process",
                    node.lineno,
                )
            elif _method_body_empty(process_fn):
                add_finding(
                    findings,
                    "PLUGIN_EMPTY_PROCESS",
                    class_loc,
                    "process 为空实现（仅 docstring/pass/...）",
                    process_fn.lineno,
                )

    if concrete_count == 0:
        add_finding(
            findings,
            "NO_CONCRETE_PLUGIN",
            package.as_posix(),
            "src/ 中未找到继承 BasePlugin/PostProcessingPlugin 的具体插件类（已跳过 src/utils）",
        )


def run_flake8(repo: Path, py_files: list[Path], findings: list[Finding]) -> None:
    """调用 flake8（含 pep8-naming）；结果一律记为 FLAKE8 warning。"""
    if not py_files:
        return
    rel_files = [repo_rel(repo, path) for path in py_files]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flake8",
            "--max-line-length=120",
            "--format=%(path)s:%(row)d:%(code)s %(text)s",
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
    """输出 GitHub Actions 注解，便于 Checks / Files changed 展示。"""
    for item in findings:
        kind = "error" if item.severity == "blocker" else "warning"
        line = item.line or 1
        print(f"::{kind} file={item.path},line={line}::{item.rule_id}: {item.message}")


def build_report(packages: list[str], findings: list[Finding]) -> dict:
    """组装 review.json 结构。"""
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

    # 包列表来源：--path 优先；否则用 --base 的变更推断；皆无则不做包级检查
    if args.path:
        packages = [Path(item) for item in args.path]
    elif args.base:
        packages = discover_packages(repo, changed_paths(repo, args.base))
    else:
        packages = []

    scan_files: list[Path] = []
    if args.path or args.base:
        if packages:
            # 识别到算法包：整包结构 / 插件 / 二进制说明 + 包内文件内容
            for package in packages:
                check_structure(repo, package, findings)
                check_native_binaries(repo, package, findings)
                check_plugins(repo, package, findings)
                for path in iter_files(repo / package):
                    scan_files.append(path)
                    check_file_content(repo, path, findings)
        elif args.base:
            # 有变更但落在包路径外：仅对变更文件做内容规则
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
    # 有阻断则非 0，供 workflow 最后一步失败
    return 1 if report["summary"]["blocker_count"] else 0


if __name__ == "__main__":
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    raise SystemExit(main())
