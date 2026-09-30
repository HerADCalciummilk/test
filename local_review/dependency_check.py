"""依赖完整性（纯静态）：依赖清单是否齐、是否自相矛盾、是否与代码 import 对得上。

清单来源全部解析并合并（requirements.txt / pyproject.toml / environment.yml /
setup.py），这样才能发现「同一个包在两个文件里版本要求矛盾」。只读文件、不装包、
不执行 setup.py。与 run_check 的「必需库保证」互补：那边管本机能不能跑，这边管
交包方有没有把依赖说清楚。
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import (
    CONDA_TO_IMPORT_NAMES,
    DEP_LIST_LIMIT,
    DEPRECATED_DISTS,
    DIST_TO_IMPORT_NAMES,
    HEAVY_DISTS,
    SKIP_DIR_NAMES,
    TEST_ONLY_IMPORTS,
)
from .models import Finding, SectionResult
from .package import PackageRef, path_is_under, read_text, repo_rel

try:  # 版本比较用；缺失时降级为「不判冲突」
    from packaging.markers import InvalidMarker, Marker
    from packaging.version import InvalidVersion, Version
except ImportError:  # pragma: no cover
    Version = None  # type: ignore[assignment]
    Marker = None  # type: ignore[assignment]
    InvalidVersion = ValueError  # type: ignore[assignment]
    InvalidMarker = ValueError  # type: ignore[assignment]

MANIFEST_NAMES = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "environment.yml",
    "environment.yaml",
    "setup.py",
)
# 非打包标准，但生态惯例（pyenv / uv 读前者，Heroku 式部署用后者）：只取 Python 版本
PYTHON_VERSION_FILES = (".python-version", "runtime.txt")
_PY_VER_RE = re.compile(r"^(?:python-)?(\d+(?:\.\d+){0,2})$")
_REQ_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")
_SPEC_RE = re.compile(r"(===|==|!=|>=|<=|~=|>|<)\s*([^,\s;<>=!~]+)")


def _join_specs(body: str) -> str:
    """把 `>=2.0,<1.26` 规整成逗号分隔，避免版本号粘连导致漏判冲突。"""
    return ",".join(f"{op}{ver}" for op, ver in _SPEC_RE.findall(body))


def _normalize_dist(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name.strip()).lower()


def _join_names(names: list[str]) -> str:
    """把同类的一批包名并成一句，超出上限只报总数，避免报告被长列表淹没。"""
    shown = names[:DEP_LIST_LIMIT]
    text = "、".join(f"`{n}`" for n in shown)
    return f"{text} 等共 {len(names)} 个" if len(names) > len(shown) else text


@dataclass(frozen=True)
class Declaration:
    """依赖清单里的一条声明。"""

    dist: str
    raw: str
    spec: str
    source: str
    line: int | None = None
    fuzzy: bool = False  # conda 的 `numpy=1.24` 属于前缀匹配
    non_pypi: bool = False  # git+ / URL / 本地路径
    marker: str = ""  # PEP 508 环境标记，如 python_version < "3.10"

    def where(self) -> str:
        return f"{self.source}:{self.line}" if self.line else self.source


def _split_marker(text: str) -> tuple[str, str]:
    """拆出 `需求 ; 环境标记`。"""
    body, _, marker = text.partition(";")
    return body.strip(), marker.strip()


def _marker_envs() -> list[dict[str, str]]:
    """用于判断标记是否互斥的候选环境网格。"""
    envs: list[dict[str, str]] = []
    platforms = (
        ("linux", "Linux", "posix", "x86_64"),
        ("win32", "Windows", "nt", "AMD64"),
        ("darwin", "Darwin", "posix", "arm64"),
    )
    for py in ("3.8", "3.9", "3.10", "3.11", "3.12", "3.13"):
        for sys_platform, system, os_name, machine in platforms:
            for extra in ("", "dev", "test"):
                envs.append({
                    "os_name": os_name,
                    "sys_platform": sys_platform,
                    "platform_machine": machine,
                    "platform_system": system,
                    "platform_release": "",
                    "platform_version": "",
                    "platform_python_implementation": "CPython",
                    "implementation_name": "cpython",
                    "implementation_version": f"{py}.0",
                    "python_version": py,
                    "python_full_version": f"{py}.0",
                    "extra": extra,
                })
    return envs


_MARKER_ENVS = _marker_envs()


def _markers_exclusive(m1: str, m2: str) -> bool:
    """两条标记是否不可能同时成立（例如按 Python 版本二选一）。

    判不出来时一律当作互斥，即放过冲突判定——宁可漏报，也不误报阻断。
    """
    if not m1 and not m2:
        return False
    if Marker is None:
        return True
    try:
        marks = [Marker(m) if m else None for m in (m1, m2)]
    except InvalidMarker:
        return True
    for env in _MARKER_ENVS:
        try:
            if all(m is None or m.evaluate(env) for m in marks):
                return False  # 存在同时成立的环境 → 真冲突
        except Exception:  # noqa: BLE001  # 标记里有认不出的变量
            return True
    return True


# ---------------------------------------------------------------- import 扫描


def collect_imports(root: Path, package: PackageRef) -> dict[str, dict[str, str]]:
    """扫描包内 .py，返回 {顶层模块: {kind: runtime|test, path, line}}。"""
    found: dict[str, dict[str, str]] = {}
    pkg_root = package.package_root(root)
    test_dir = package.test_dir(root)

    files: list[Path] = []
    for base in (pkg_root, package.source_dir(root), test_dir):
        if base.is_dir():
            files.extend(base.rglob("*.py"))

    for path in sorted(set(files)):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name == "setup.py":
            continue  # 打包脚本，import 的是构建工具而非算法依赖
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        kind = "test" if path_is_under(path, test_dir) else "runtime"
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # 相对导入是包内模块
                    continue
                if node.module:
                    names = [node.module.split(".")[0]]
            for name in names:
                cur = found.get(name)
                if cur is not None and not (
                    cur["kind"] == "test" and kind == "runtime"
                ):
                    continue
                found[name] = {
                    "kind": kind,
                    "path": repo_rel(root, path),
                    "line": str(getattr(node, "lineno", "") or ""),
                }
    return found


def _repo_internal_names(root: Path, package: PackageRef) -> set[str]:
    """仓库内其他包与公共库的顶层名。

    这类导入（如 `from NIMM.utils import x`）是仓库内部依赖：代码就在同一个仓库里，
    不需要 pip 安装，也不该写进依赖清单，因此不能按「未声明的第三方库」处理。
    """
    names: set[str] = set()

    def _add_children(base: Path) -> None:
        if not base.is_dir():
            return
        for child in base.iterdir():
            if child.name.startswith(".") or child.name in SKIP_DIR_NAMES:
                continue
            if child.is_dir():
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)

    _add_children(root)
    nimm = root / "NIMM"
    _add_children(nimm)  # utils 等公共库、各 kind 目录
    if nimm.is_dir():
        for kind_dir in nimm.iterdir():
            if kind_dir.is_dir() and not kind_dir.name.startswith("."):
                _add_children(kind_dir)  # 同类下的其他算法包
    pkg_root = package.package_root(root)
    _add_children(pkg_root.parent)  # 中间包的同级包
    names.discard(pkg_root.name)
    return names


def _local_module_names(root: Path, package: PackageRef) -> set[str]:
    """包内自有模块名：不算外部依赖。"""
    names: set[str] = set()
    bases = [
        package.package_root(root),
        package.source_dir(root),
        package.cli_dir(root),
        package.test_dir(root),
    ]
    for base in bases:
        if not base.is_dir():
            continue
        names.add(base.name)
        for child in base.iterdir():
            if child.is_dir() and child.name not in SKIP_DIR_NAMES:
                names.add(child.name)
            elif child.suffix == ".py":
                names.add(child.stem)
    return names


# ------------------------------------------------------------------ 清单解析


def _looks_non_pypi(line: str) -> bool:
    return "git+" in line or "://" in line or line.startswith((".", "/", "\\"))


def _parse_requirements(
    root: Path, path: Path, seen: set[Path] | None = None
) -> tuple[list[Declaration], list[tuple[str, str]]]:
    seen = seen if seen is not None else set()
    resolved = path.resolve()
    if resolved in seen or not path.is_file():
        return [], []
    seen.add(resolved)
    text = read_text(path)
    if text is None:
        return [], [(repo_rel(root, path), f"{repo_rel(root, path)} 无法读取")]

    decls: list[Declaration] = []
    notes: list[tuple[str, str]] = []
    source = repo_rel(root, path)
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith(("-r", "--requirement")):
            ref = line.split(None, 1)[-1].strip()
            sub_decls, sub_notes = _parse_requirements(root, path.parent / ref, seen)
            decls.extend(sub_decls)
            notes.extend(sub_notes)
            continue
        if line.startswith("-"):  # -e . / --index-url 等
            continue
        body, marker = _split_marker(line)
        if "#egg=" in body:
            name = body.split("#egg=", 1)[1]
            decls.append(
                Declaration(
                    dist=_normalize_dist(name),
                    raw=name,
                    spec="",
                    source=source,
                    line=lineno,
                    non_pypi=True,
                )
            )
            continue
        match = _REQ_NAME_RE.match(body)
        if not match:
            if _looks_non_pypi(body):
                notes.append(
                    (source, f"{source}:{lineno} 是 URL/路径依赖，无法确定包名")
                )
            continue
        name = match.group(0)
        spec = _join_specs(body)
        decls.append(
            Declaration(
                dist=_normalize_dist(name),
                raw=name,
                spec=spec,
                source=source,
                line=lineno,
                non_pypi=_looks_non_pypi(body),
                marker=marker,
            )
        )
    return decls, notes


def _parse_pyproject(
    root: Path, path: Path
) -> tuple[list[Declaration], list[str], list[tuple[str, str]]]:
    """返回 (依赖, python 版本约束, 备注)；备注为 (来源文件, 说明)。"""
    text = read_text(path)
    source = repo_rel(root, path)
    if text is None:
        return [], [], [(source, f"{source} 无法读取")]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [], [(source, f"{source} 解析失败：{exc}")]

    decls: list[Declaration] = []
    pythons: list[str] = []

    def _add(raw_req: str) -> None:
        body, marker = _split_marker(raw_req)
        match = _REQ_NAME_RE.match(body)
        if not match:
            return
        name = match.group(0)
        spec = _join_specs(body)
        decls.append(
            Declaration(
                dist=_normalize_dist(name),
                raw=name,
                spec=spec,
                source=source,
                non_pypi=_looks_non_pypi(body),
                marker=marker,
            )
        )

    project = data.get("project") or {}
    if isinstance(project.get("requires-python"), str):
        pythons.append(project["requires-python"])
    for req in project.get("dependencies") or []:
        if isinstance(req, str):
            _add(req)
    for group in (project.get("optional-dependencies") or {}).values():
        for req in group or []:
            if isinstance(req, str):
                _add(req)

    poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}
    for name, constraint in poetry.items():
        if name.lower() == "python":
            if isinstance(constraint, str):
                pythons.append(constraint)
            continue
        spec = constraint if isinstance(constraint, str) else ""
        decls.append(
            Declaration(
                dist=_normalize_dist(name),
                raw=name,
                spec=spec if spec.startswith(("=", ">", "<", "!", "~")) else "",
                source=source,
            )
        )
    return decls, pythons, []


def _parse_environment_yml(
    root: Path, path: Path
) -> tuple[list[Declaration], list[str], list[tuple[str, str]]]:
    """行式解析 conda environment.yml 的 dependencies 块（含嵌套 pip 列表）。"""
    text = read_text(path)
    source = repo_rel(root, path)
    if text is None:
        return [], [], [(source, f"{source} 无法读取")]

    decls: list[Declaration] = []
    pythons: list[str] = []
    in_deps = False
    deps_indent = 0
    in_pip = False
    pip_indent = 0

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if not in_deps:
            if stripped.startswith("dependencies:"):
                in_deps = True
                deps_indent = indent
            continue
        if indent <= deps_indent and not stripped.startswith("-"):
            break  # dependencies 块结束
        if not stripped.startswith("-"):
            continue

        item = stripped[1:].strip()
        if item.startswith("pip:"):
            in_pip = True
            pip_indent = indent
            continue
        if in_pip and indent <= pip_indent:
            in_pip = False
        if not item:
            continue

        body, marker = _split_marker(item)
        match = _REQ_NAME_RE.match(body)
        if not match:
            continue
        name = match.group(0)
        if _normalize_dist(name) == "python":
            rest = body[len(name):].strip()
            pythons.append(rest or "")
            continue
        spec = _join_specs(body)
        fuzzy = False
        if not spec:
            # conda 的单等号 `numpy=1.24` 是前缀匹配
            single = re.match(r"^[A-Za-z0-9._-]+=([^=].*)$", body)
            if single:
                spec = f"=={single.group(1).strip()}"
                fuzzy = True
        decls.append(
            Declaration(
                dist=_normalize_dist(name),
                raw=name,
                spec=spec,
                source=source,
                line=lineno,
                fuzzy=fuzzy and not in_pip,
                marker=marker,
            )
        )
    return decls, pythons, []


def _parse_python_version_files(
    root: Path, pkg_root: Path
) -> tuple[list[str], list[str]]:
    """从 `.python-version` / `runtime.txt` 取 Python 版本，返回 (约束, 来源文件)。

    这两个文件不是依赖清单，只补 Python 版本这一项，因此不参与 DEP_NO_MANIFEST。
    认不出内容（如 `pypy3.10-7.3.12`）时静默跳过，不记 unparsed——否则会连带把
    未声明依赖的结论降级，代价与收益不成比例。
    """
    specs: list[str] = []
    sources: list[str] = []
    for name in PYTHON_VERSION_FILES:
        path = pkg_root / name
        if not path.is_file():
            continue
        found: list[str] = []
        for raw in (read_text(path) or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            match = _PY_VER_RE.match(line) if line else None
            if match:
                found.append(f"=={match.group(1)}")
        if found:
            specs.extend(found)
            sources.append(repo_rel(root, path))
    return specs, sources


def _literal_str_list(node: ast.AST) -> list[str] | None:
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return None


def _parse_setup_py(
    root: Path, path: Path
) -> tuple[list[Declaration], list[str], list[tuple[str, str]]]:
    """只读 AST 字面量，不执行 setup.py。"""
    text = read_text(path)
    source = repo_rel(root, path)
    if text is None:
        return [], [], [(source, f"{source} 无法读取")]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return [], [], [(source, f"{source} 语法错误，未解析依赖")]

    assigned: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                items = _literal_str_list(node.value)
                if items is not None:
                    assigned[target.id] = items

    decls: list[Declaration] = []
    pythons: list[str] = []
    notes: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name != "setup":
            continue
        for kw in node.keywords:
            if kw.arg == "python_requires":
                if isinstance(kw.value, ast.Constant) and isinstance(
                    kw.value.value, str
                ):
                    pythons.append(kw.value.value)
            elif kw.arg == "install_requires":
                items = _literal_str_list(kw.value)
                if items is None and isinstance(kw.value, ast.Name):
                    items = assigned.get(kw.value.id)
                if items is None:
                    notes.append(
                        (source, f"{source} 的 install_requires 非字面量，无法静态解析")
                    )
                    continue
                for req in items:
                    body, marker = _split_marker(req)
                    match = _REQ_NAME_RE.match(body)
                    if not match:
                        continue
                    dist_name = match.group(0)
                    spec = _join_specs(body)
                    decls.append(
                        Declaration(
                            dist=_normalize_dist(dist_name),
                            raw=dist_name,
                            spec=spec,
                            source=source,
                            non_pypi=_looks_non_pypi(body),
                            marker=marker,
                        )
                    )
    return decls, pythons, notes


# ------------------------------------------------------------------ 冲突判定


def _version(text: str):
    if Version is None:
        return None
    try:
        return Version(text.rstrip(".*"))
    except InvalidVersion:
        return None


def _prefix_compatible(a: str, b: str) -> bool:
    pa = a.rstrip(".*").split(".")
    pb = b.rstrip(".*").split(".")
    n = min(len(pa), len(pb))
    return pa[:n] == pb[:n]


@dataclass
class ConflictResult:
    """一个包的冲突判定结果。"""

    conflict: tuple[str, Declaration, Declaration] | None = None
    # 版本本来矛盾、但环境标记互斥（如按 Python 版本二选一），不算冲突
    marker_split: list[tuple[str, Declaration, Declaration]] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.marker_split is None:
            self.marker_split = []


def _conflict_reason(group: list[Declaration]) -> ConflictResult:
    """判定确定性冲突：不同钉版本、下界高于上界、钉版本越界。

    两条声明的环境标记互斥时（`; python_version<"3.10"` 与 `>=3.10`），
    实际不可能同时安装，记为 marker_split 而非冲突。
    """
    result = ConflictResult()
    pins: list[tuple[Declaration, str]] = []
    lowers: list[tuple[Declaration, str, bool]] = []  # (decl, ver, 含等号)
    uppers: list[tuple[Declaration, str, bool]] = []
    for decl in group:
        for op, ver in _SPEC_RE.findall(decl.spec):
            if op in ("==", "==="):
                pins.append((decl, ver))
            elif op in (">=", ">"):
                lowers.append((decl, ver, op == ">="))
            elif op in ("<=", "<"):
                uppers.append((decl, ver, op == "<="))

    def _record(reason: str, d1: Declaration, d2: Declaration) -> bool:
        """返回 True 表示已确认为冲突，可以停止继续找。"""
        if d1 is not d2 and _markers_exclusive(d1.marker, d2.marker):
            result.marker_split.append((reason, d1, d2))
            return False
        result.conflict = (reason, d1, d2)
        return True

    for i, (d1, v1) in enumerate(pins):
        for d2, v2 in pins[i + 1:]:
            if _prefix_compatible(v1, v2):
                continue
            if _record(f"分别钉在 `{v1}` 与 `{v2}`", d1, d2):
                return result

    if Version is None:
        return result

    for d_low, v_low, low_eq in lowers:
        lo = _version(v_low)
        if lo is None:
            continue
        for d_up, v_up, up_eq in uppers:
            up = _version(v_up)
            if up is None:
                continue
            if lo > up or (lo == up and not (low_eq and up_eq)):
                if _record(f"下界 `{v_low}` 高于上界 `{v_up}`", d_low, d_up):
                    return result
        for d_pin, v_pin in pins:
            pin = _version(v_pin)
            if pin is None:
                continue
            if pin < lo or (pin == lo and not low_eq):
                if _record(f"钉版本 `{v_pin}` 不满足下界 `{v_low}`", d_pin, d_low):
                    return result
    for d_up, v_up, up_eq in uppers:
        up = _version(v_up)
        if up is None:
            continue
        for d_pin, v_pin in pins:
            pin = _version(v_pin)
            if pin is None:
                continue
            if pin > up or (pin == up and not up_eq):
                if _record(f"钉版本 `{v_pin}` 不满足上界 `{v_up}`", d_pin, d_up):
                    return result
    return result


# -------------------------------------------------------------------- 主流程


def _declared_import_names(dists: set[str]) -> set[str]:
    names: set[str] = set()
    for dist in dists:
        names.add(dist)
        names.add(dist.replace("_", ""))
        names |= {_normalize_dist(n) for n in DIST_TO_IMPORT_NAMES.get(dist, ())}
        names |= {_normalize_dist(n) for n in CONDA_TO_IMPORT_NAMES.get(dist, ())}
    return names


def check_dependencies(root: Path, package: PackageRef) -> SectionResult:
    """依赖清单发现 → 解析 → 逐项判定（未声明/冲突/停维护/重量级/总数等）。"""
    section = SectionResult(name="dependencies")
    pkg_root = package.package_root(root)
    if not pkg_root.is_dir():
        section.skipped = True
        section.skip_reason = "包根不存在"
        return section

    manifests = [pkg_root / name for name in MANIFEST_NAMES if (pkg_root / name).is_file()]
    decls: list[Declaration] = []
    pythons: list[str] = []
    notes: list[tuple[str, str]] = []
    for path in manifests:
        if path.name.startswith("requirements"):
            d, n = _parse_requirements(root, path)
            decls += d
            notes += n
        elif path.name == "pyproject.toml":
            d, p, n = _parse_pyproject(root, path)
            decls += d
            pythons += p
            notes += n
        elif path.name in ("environment.yml", "environment.yaml"):
            d, p, n = _parse_environment_yml(root, path)
            decls += d
            pythons += p
            notes += n
        elif path.name == "setup.py":
            d, p, n = _parse_setup_py(root, path)
            decls += d
            pythons += p
            notes += n

    py_specs, py_files = _parse_python_version_files(root, pkg_root)
    pythons += py_specs

    by_dist: dict[str, list[Declaration]] = {}
    for decl in decls:
        by_dist.setdefault(decl.dist, []).append(decl)

    imports = collect_imports(root, package)
    local_names = _local_module_names(root, package)
    repo_names = _repo_internal_names(root, package) - local_names
    stdlib = set(sys.stdlib_module_names)
    outside: dict[str, dict[str, str]] = {
        name: info
        for name, info in imports.items()
        if name not in stdlib and name not in local_names and not name.startswith("_")
    }
    repo_internal = {n: i for n, i in outside.items() if n in repo_names}
    third_party = {n: i for n, i in outside.items() if n not in repo_names}

    declared_imports = _declared_import_names(set(by_dist))
    undeclared: list[tuple[str, dict[str, str]]] = []
    for name, info in sorted(third_party.items()):
        if _normalize_dist(name) in declared_imports:
            continue
        if info["kind"] == "test" and name in TEST_ONLY_IMPORTS:
            continue
        undeclared.append((name, info))

    # 仓库内部依赖也算「用到了」：真被 import 了，不该再报「声明了却没 import」
    used_norm = {_normalize_dist(n) for n in (*third_party, *repo_internal)}
    used_norm |= {n.replace("_", "") for n in used_norm}
    unused = sorted(
        dist
        for dist in by_dist
        if dist not in used_norm
        and not (
            {
                _normalize_dist(x)
                for x in (
                    *DIST_TO_IMPORT_NAMES.get(dist, ()),
                    *CONDA_TO_IMPORT_NAMES.get(dist, ()),
                )
            }
            & used_norm
        )
    )

    conflicts: list[tuple[str, str, Declaration, Declaration]] = []
    marker_splits: list[tuple[str, str, Declaration, Declaration]] = []
    for dist, group in sorted(by_dist.items()):
        found = _conflict_reason(group)
        if found.conflict:
            reason, d1, d2 = found.conflict
            conflicts.append((dist, reason, d1, d2))
        for reason, d1, d2 in found.marker_split:
            marker_splits.append((dist, reason, d1, d2))

    specs = [bool(d.spec) for group in by_dist.values() for d in group]
    section.metrics = {
        "manifests": [repo_rel(root, p) for p in manifests],
        "declared_count": len(by_dist),
        # 全无版本约束 → 环境无法复现；不单独出条目，由报告的依赖基准行呈现
        "unconstrained": len(by_dist) >= 3 and not any(specs),
        "python_requires": pythons,
        "python_version_files": py_files,
        "third_party_imports": sorted(third_party),
        "repo_internal_imports": sorted(repo_internal),
        "undeclared": [name for name, _ in undeclared],
        # 有清单没解析出来时，未声明结论只能算「疑似」
        "undeclared_uncertain": bool(notes),
        "unused_declared": unused,
        "conflicts": [f"{d}: {reason}" for d, reason, _, _ in conflicts],
        "marker_splits": [f"{d}: {reason}" for d, reason, _, _ in marker_splits],
    }

    _emit_findings(
        section,
        root=root,
        package=package,
        manifests=manifests,
        by_dist=by_dist,
        pythons=pythons,
        notes=notes,
        undeclared=undeclared,
        unused=unused,
        conflicts=conflicts,
        split_dists={dist for dist, _, _, _ in marker_splits},
        third_party=third_party,
        repo_internal=repo_internal,
    )
    return section


def _emit_findings(
    section: SectionResult,
    *,
    root: Path,
    package: PackageRef,
    manifests: list[Path],
    by_dist: dict[str, list[Declaration]],
    pythons: list[str],
    notes: list[tuple[str, str]],
    undeclared: list[tuple[str, dict[str, str]]],
    unused: list[str],
    conflicts: list[tuple[str, str, Declaration, Declaration]],
    split_dists: set[str],
    third_party: dict[str, dict[str, str]],
    repo_internal: dict[str, dict[str, str]],
) -> None:
    add = section.findings.append
    pkg_id = package.package_id

    if not manifests:
        add(
            Finding(
                rule_id="DEP_NO_MANIFEST",
                severity="warning",
                path=pkg_id,
                message=(
                    "未找到任何依赖清单（requirements.txt / pyproject.toml / "
                    "environment.yml / setup.py），换机器无法复现环境"
                ),
            )
        )
    for note_source, note in notes:
        add(
            Finding(
                rule_id="DEP_MANIFEST_UNPARSED",
                severity="info",
                path=note_source,
                message=note,
            )
        )

    for dist, reason, d1, d2 in conflicts:
        marks = "；".join(m for m in (d1.marker, d2.marker) if m)
        tail = f"；环境标记：{marks}" if marks else ""
        add(
            Finding(
                rule_id="DEP_VERSION_CONFLICT",
                severity="blocker",
                path=d1.where(),
                message=(
                    f"依赖 `{dist}` 版本要求矛盾：{reason}"
                    f"（{d1.where()} 与 {d2.where()}）{tail}"
                ),
            )
        )

    conflict_dists = {dist for dist, _, _, _ in conflicts}
    duplicated: list[tuple[str, Declaration]] = []
    for dist, group in sorted(by_dist.items()):
        if len(group) < 2 or dist in conflict_dists:
            continue
        if dist in split_dists or all(d.marker for d in group):
            continue  # 带环境标记的条件依赖本就该分开写
        places = sorted({d.where() for d in group})
        if len(places) < 2:
            continue
        duplicated.append((f"`{dist}`（{'、'.join(places)}）", group[0]))
    if duplicated:
        add(
            Finding(
                rule_id="DEP_DUPLICATE_DECLARED",
                severity="info",
                path=duplicated[0][1].source,
                line=duplicated[0][1].line,
                message=(
                    "以下依赖在多处声明，建议各自只保留一处："
                    f"{'；'.join(t for t, _ in duplicated)}"
                ),
            )
        )

    if not pythons and manifests:
        # 只有 requirements.txt 时无处可写，属清单格式局限而非交包方漏写
        declarable = [
            p
            for p in manifests
            if p.name in ("pyproject.toml", "setup.py", "environment.yml", "environment.yaml")
        ]
        # 指向该写的那份清单；只有 requirements.txt 时指向它，便于直接打开
        target = repo_rel(root, (declarable or manifests)[0])
        add(
            Finding(
                rule_id="DEP_NO_PYTHON_VERSION",
                severity="warning" if declarable else "info",
                path=target,
                message=(
                    f"未声明 Python 版本要求（包内有 {'、'.join(p.name for p in declarable)}"
                    "，可写明）"
                    if declarable
                    else "未声明 Python 版本要求；requirements.txt 无此字段（注释不算），"
                    "可加 pyproject.toml 的 requires-python，或放一行 `.python-version`"
                ),
            )
        )

    deprecated = [
        (f"`{group[0].raw}` {DEPRECATED_DISTS[dist]}", group[0])
        for dist, group in sorted(by_dist.items())
        if dist in DEPRECATED_DISTS
    ]
    if deprecated:
        add(
            Finding(
                rule_id="DEP_DEPRECATED",
                severity="warning",
                path=deprecated[0][1].source,
                line=deprecated[0][1].line,
                message=f"清单含已停止维护的依赖：{'；'.join(t for t, _ in deprecated)}",
            )
        )

    heavy = [(dist, by_dist[dist][0]) for dist in sorted(by_dist) if dist in HEAVY_DISTS]
    if heavy:
        add(
            Finding(
                rule_id="DEP_HEAVY",
                severity="info",
                path=heavy[0][1].source,
                line=heavy[0][1].line,
                message=(
                    f"重量级依赖 {_join_names([d for d, _ in heavy])}："
                    "请确认算法确实需要，否则会显著拉高部署成本"
                ),
            )
        )

    non_pypi = [
        (dist, next(d for d in group if d.non_pypi))
        for dist, group in sorted(by_dist.items())
        if any(d.non_pypi for d in group)
    ]
    if non_pypi:
        add(
            Finding(
                rule_id="DEP_NON_PYPI_SOURCE",
                severity="info",
                path=non_pypi[0][1].source,
                line=non_pypi[0][1].line,
                message=(
                    f"依赖 {_join_names([d for d, _ in non_pypi])} "
                    "指向 URL/仓库/本地路径，换机器可能装不上"
                ),
            )
        )

    # 有清单片段没解析出来（见 DEP_MANIFEST_UNPARSED）时，未读到的声明会被误判为
    # 未声明，故一律降为 info 并在消息里点明不确定性。
    unparsed = bool(notes)
    hedge = "（本包有未解析的清单片段，可能实为已声明）" if unparsed else ""
    for name, info in undeclared[:DEP_LIST_LIMIT]:
        scope = "测试" if info["kind"] == "test" else "运行时"
        runtime = info["kind"] == "runtime"
        add(
            Finding(
                rule_id="DEP_UNDECLARED",
                severity="warning" if runtime and not unparsed else "info",
                path=info["path"],
                line=int(info["line"]) if info["line"].isdigit() else None,
                message=f"{scope}依赖 `{name}` 未在依赖清单中声明{hedge}",
            )
        )
    if len(undeclared) > DEP_LIST_LIMIT:
        add(
            Finding(
                rule_id="DEP_UNDECLARED",
                severity="info",
                path=pkg_id,
                message=(
                    f"另有 {len(undeclared) - DEP_LIST_LIMIT} 个未声明依赖未逐条列出"
                    f"{hedge}"
                ),
            )
        )

    if repo_internal:
        first = min(repo_internal.items())[1]
        add(
            Finding(
                rule_id="DEP_REPO_INTERNAL",
                severity="info",
                path=first["path"],
                line=int(first["line"]) if first["line"].isdigit() else None,
                message=(
                    f"{_join_names(sorted(repo_internal))} 是仓库内其他包或公共库，"
                    "属仓库内部依赖，无需写进依赖清单；但本包因此不能脱离仓库单独交付"
                ),
            )
        )

    if unused:
        first_unused = by_dist[unused[0]][0]
        add(
            Finding(
                rule_id="DEP_UNUSED_DECLARED",
                severity="info",
                path=first_unused.source,
                line=first_unused.line,
                message=(
                    f"清单声明了 {_join_names(unused)}，但代码中未见 import"
                    "（只会多装无用的包，不影响运行）"
                ),
            )
        )
    del third_party  # 已在 metrics 中体现
