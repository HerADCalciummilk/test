"""动态检查：为包创建虚拟环境并运行 pytest。

默认由一键入口调用；可用 --skip-run / --dry-run 跳过。
仅含 venv + pytest（不含 cli command / 出图）。

虚拟环境默认建在系统临时目录并在跑完删除，避免在算法包内留下未被
.gitignore 覆盖的目录；`--venv` 指定的目录视为可复用缓存，不会删除。
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path
from typing import Iterable

from .config import (
    PROBE_EXTRA_LIBS,
    REQUIRED_RUNTIME_LIBS,
    RUNTIME_LIB_ALIASES,
)
from .dependency_check import collect_imports
from .models import Finding, SectionResult
from .package import PackageRef, load_run_config, repo_rel

LOG_LIMIT = 8_000
DEFAULT_TIMEOUT_SEC = 300


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _ensure_venv(venv_dir: Path, *, system_site: bool) -> Path:
    py = _venv_python(venv_dir)
    if py.is_file():
        return py
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    # 默认继承本机库：算法包多依赖 numpy/meteva_base 等大件，全隔离会让 pytest
    # 因缺依赖收集失败，掩盖真正要看的算法问题。
    venv.create(
        str(venv_dir),
        with_pip=True,
        clear=False,
        system_site_packages=system_site,
    )
    return _venv_python(venv_dir)


def _remove_venv(venv_dir: Path) -> bool:
    """尽力删除临时 venv；Windows 上偶有占用，失败返回 False 而不抛错。"""

    def _clear_readonly(func, path, _exc) -> None:
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    kwargs = (
        {"onexc": _clear_readonly}
        if sys.version_info >= (3, 12)
        else {"onerror": _clear_readonly}
    )
    for attempt in range(3):
        if not venv_dir.exists():
            return True
        shutil.rmtree(venv_dir, **kwargs)
        if not venv_dir.exists():
            return True
        time.sleep(0.5 * (attempt + 1))
    return not venv_dir.exists()


def _pip_install(py: Path, *args: str, timeout: int = 600) -> tuple[int, str]:
    cmd = [str(py), "-m", "pip", "install", "--disable-pip-version-check", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out[-LOG_LIMIT:]


PROBE_LIBS = tuple(dict.fromkeys((*REQUIRED_RUNTIME_LIBS, *PROBE_EXTRA_LIBS)))

_ENV_PROBE = '''
import importlib.metadata as md
import importlib.util
import json
import platform

libs = {}
for name in __LIBS__:
    try:
        if importlib.util.find_spec(name) is None:
            continue
    except Exception:
        continue
    try:
        libs[name] = md.version(name)
    except Exception:
        libs[name] = "?"

print(json.dumps({
    "python": platform.python_version(),
    "platform": platform.platform(),
    "libs": libs,
}))
'''


def _probe_env(py: Path) -> dict:
    """记录 pytest 实际运行环境，便于区分失败是环境问题还是代码问题。"""
    code = _ENV_PROBE.replace("__LIBS__", json.dumps(list(PROBE_LIBS)))
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        data = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return {}
    libs = data.get("libs") or {}
    return {
        "python": str(data.get("python") or ""),
        "platform": str(data.get("platform") or ""),
        "pytest": str(libs.pop("pytest", "")),
        "libs": {k: str(v) for k, v in libs.items()},
    }


_MISSING_PROBE = '''
import importlib.util
import json

missing = []
for name in __LIBS__:
    try:
        found = importlib.util.find_spec(name) is not None
    except Exception:
        found = False
    if not found:
        missing.append(name)
print(json.dumps(missing))
'''


def _missing_libs(py: Path, names: Iterable[str]) -> list[str]:
    names = list(names)
    if not names:
        return []
    code = _MISSING_PROBE.replace("__LIBS__", json.dumps(names))
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return list(json.loads((proc.stdout or "").strip().splitlines()[-1]))
    except Exception:  # noqa: BLE001
        return names


def _imported_top_modules(root: Path, package: PackageRef) -> set[str]:
    """包里实际 import 了哪些顶层模块（判断缺库是否真的挡住本包）。"""
    return set(collect_imports(root, package))


def _ensure_required_libs(
    root: Path,
    package: PackageRef,
    section: SectionResult,
    *,
    py: Path,
) -> dict[str, str]:
    """保证必需库在 venv 里可用：缺的就装，装不上按环境问题上报。"""
    status: dict[str, str] = {}
    # 别名一起探：代码里可能写 `import meteva_base as meb`，环境里两种都算有
    probe_names = [
        n
        for lib in REQUIRED_RUNTIME_LIBS
        for n in (lib, *RUNTIME_LIB_ALIASES.get(lib, ()))
    ]
    absent = set(_missing_libs(py, probe_names))

    def _is_missing(lib: str) -> bool:
        names = {lib, *RUNTIME_LIB_ALIASES.get(lib, ())}
        return names <= absent

    missing = [lib for lib in REQUIRED_RUNTIME_LIBS if _is_missing(lib)]
    for lib in REQUIRED_RUNTIME_LIBS:
        if lib not in missing:
            status[lib] = "present"

    install_logs: dict[str, str] = {}
    for name in missing:
        code, log = _pip_install(py, REQUIRED_RUNTIME_LIBS[name])
        install_logs[name] = log
        status[name] = "installed" if code == 0 else "install_failed"

    still_missing: list[str] = []
    if missing:
        absent = set(_missing_libs(py, [
            n for lib in missing for n in (lib, *RUNTIME_LIB_ALIASES.get(lib, ()))
        ]))
        still_missing = [lib for lib in missing if _is_missing(lib)]
    if not still_missing:
        return status

    pkg_imports = _imported_top_modules(root, package)
    for name in still_missing:
        status[name] = "missing"
        import_names = {name, *RUNTIME_LIB_ALIASES.get(name, ())}
        needed = name == "pytest" or bool(import_names & pkg_imports)
        hint = (
            "请检查网络或 pip 源（需私有源/本地 wheel 时设 pip 自身的 PIP_INDEX_URL"
            " / PIP_FIND_LINKS 环境变量）"
        )
        section.findings.append(
            Finding(
                rule_id="EXEC_MISSING_REQUIRED_LIB",
                severity="blocker" if needed else "warning",
                path=package.package_id,
                message=(
                    f"运行环境缺少必需库 `{name}`"
                    + ("（本包代码用到它，测试结果不可信）" if needed else "（本包未 import，暂不影响）")
                    + f"；{hint}"
                ),
                evidence=install_logs.get(name, "")[-800:],
            )
        )
    return status


def _resolve_requirements(root: Path, package: PackageRef, cfg: dict) -> Path | None:
    explicit = (cfg.get("requirements") or "").strip()
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = package.package_root(root) / p
        return p if p.is_file() else None
    pkg_root = package.package_root(root)
    for name in ("requirements.txt", "requirements-dev.txt"):
        cand = pkg_root / name
        if cand.is_file():
            return cand
    return None


def _build_env(root: Path, package: PackageRef) -> dict[str, str]:
    env = os.environ.copy()
    src = package.source_dir(root)
    parts = [str(src)] if src.is_dir() else []
    old = env.get("PYTHONPATH", "")
    if old:
        parts.append(old)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> tuple[int, str, float]:
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        log = ((proc.stdout or "") + (proc.stderr or ""))[-LOG_LIMIT:]
        return proc.returncode, log, time.time() - t0
    except subprocess.TimeoutExpired as exc:
        log = ((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        log += ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return 124, (log + f"\n[timeout after {timeout}s]")[-LOG_LIMIT:], time.time() - t0


def _test_py_files(test_dir: Path) -> list[Path]:
    if not test_dir.is_dir():
        return []
    files: list[Path] = []
    for p in test_dir.rglob("*.py"):
        if p.name == "__init__.py":
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            files.append(p)
    return files


def run_execution_checks(
    root: Path,
    package: PackageRef,
    *,
    report_md_path: Path,
    venv_dir: Path | None = None,
    keep_venv: bool = False,
    isolated_venv: bool = False,
    skip_run: bool = False,
) -> SectionResult:
    """创建 venv 并 pytest 包内 test/；临时 venv 跑完即删。"""
    del report_md_path  # 接口兼容；本实现不写旁路产物
    section = SectionResult(name="execution")
    if skip_run:
        section.skipped = True
        section.skip_reason = "用户指定跳过实跑"
        return section

    cfg = load_run_config(root, package)
    timeout = int(cfg.get("timeout_sec") or DEFAULT_TIMEOUT_SEC)
    pkg_root = package.package_root(root)
    test_dir = package.test_dir(root)
    test_files = _test_py_files(test_dir)
    runs: list[dict] = []
    section.metrics = {"runs": runs}

    if not test_dir.is_dir():
        section.findings.append(
            Finding(
                rule_id="EXEC_NO_TEST_DIR",
                severity="blocker",
                path=repo_rel(root, test_dir),
                message="缺少 test/ 目录，无法运行 pytest",
            )
        )
        return section

    if not test_files:
        section.findings.append(
            Finding(
                rule_id="EXEC_NO_TESTS",
                severity="blocker",
                path=repo_rel(root, test_dir),
                message="test/ 下未发现 test_*.py / *_test.py",
            )
        )
        return section

    # 未显式指定时用临时目录，跑完删除：不在算法包内留残留
    reuse_venv = venv_dir is not None
    if venv_dir is None:
        venv_dir = Path(tempfile.mkdtemp(prefix="local-review-venv-"))
    try:
        py = _ensure_venv(venv_dir, system_site=not isolated_venv)
    except Exception as exc:  # noqa: BLE001
        section.findings.append(
            Finding(
                rule_id="EXEC_VENV_FAILED",
                severity="blocker",
                path=package.package_id,
                message=f"创建虚拟环境失败: {exc}",
                evidence=str(venv_dir),
            )
        )
        if not reuse_venv and not keep_venv:
            _remove_venv(venv_dir)
        return section

    section.metrics["venv"] = str(venv_dir)
    section.metrics["python"] = str(py)
    section.metrics["venv_reused"] = reuse_venv
    section.metrics["site_packages"] = "isolated" if isolated_venv else "inherited"
    section.metrics["base_python"] = sys.executable

    try:
        _install_and_pytest(
            root,
            package,
            section,
            py=py,
            cfg=cfg,
            timeout=timeout,
            pkg_root=pkg_root,
            test_dir=test_dir,
            test_files=test_files,
            runs=runs,
        )
    finally:
        if reuse_venv or keep_venv:
            section.metrics["venv_removed"] = False
            section.metrics["venv_disposition"] = "reuse" if reuse_venv else "kept"
        else:
            removed = _remove_venv(venv_dir)
            section.metrics["venv_removed"] = removed
            section.metrics["venv_disposition"] = (
                "removed" if removed else "cleanup_failed"
            )
            if not removed:
                section.findings.append(
                    Finding(
                        rule_id="EXEC_VENV_CLEANUP_FAILED",
                        severity="info",
                        path=str(venv_dir),
                        message="临时虚拟环境未能删除，请手动清理",
                    )
                )
    return section


def _install_and_pytest(
    root: Path,
    package: PackageRef,
    section: SectionResult,
    *,
    py: Path,
    cfg: dict,
    timeout: int,
    pkg_root: Path,
    test_dir: Path,
    test_files: list[Path],
    runs: list[dict],
) -> None:
    """在已就绪的 venv 里备齐必需库、装包依赖并跑 pytest，结果写入 section。"""
    req = _resolve_requirements(root, package, cfg)
    if req is not None:
        code, pip_log = _pip_install(py, "-r", str(req))
        section.metrics["requirements"] = str(req)
        if code != 0:
            section.findings.append(
                Finding(
                    rule_id="EXEC_PIP_FAILED",
                    severity="blocker",
                    path=repo_rel(root, req),
                    message="安装包依赖失败",
                    evidence=pip_log[-1500:],
                )
            )
            return

    # 必需库放在包依赖之后校验：requirements 可能已经带上了它们
    lib_status = _ensure_required_libs(root, package, section, py=py)
    section.metrics["required_libs"] = lib_status
    section.metrics["env"] = _probe_env(py)
    if lib_status.get("pytest") == "missing":
        return  # 连 pytest 都没有，跑不了；已记 blocker

    env = _build_env(root, package)
    # no:cacheprovider：不在算法包里写 .pytest_cache
    cmd = [
        str(py), "-m", "pytest", str(test_dir),
        "-q", "--tb=short", "-p", "no:cacheprovider",
    ]
    code, log, elapsed = _run_cmd(cmd, cwd=pkg_root, env=env, timeout=timeout)
    runs.append({
        "kind": "pytest",
        "command": cmd,
        "exit_code": code,
        "elapsed_sec": round(elapsed, 2),
        "log_tail": log[-2000:],
    })
    if code != 0:
        section.findings.append(
            Finding(
                rule_id="EXEC_PYTEST_FAILED",
                severity="blocker",
                path=repo_rel(root, test_dir),
                message="pytest 未全部通过",
                evidence=log[-1500:],
            )
        )
    else:
        section.findings.append(
            Finding(
                rule_id="EXEC_PYTEST_OK",
                severity="info",
                path=repo_rel(root, test_dir),
                message=f"pytest 通过（{len(test_files)} 个测试文件，{elapsed:.1f}s）",
            )
        )
