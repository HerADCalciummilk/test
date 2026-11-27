# -*- coding: utf-8 -*-
"""按模块名引入子模块的 ``process``，再把参数传进去运行。

``module`` 对应 ``cli/{模块}_cli.py``。参数原样交给这个 ``process``，
由它自己的 ``@merge_params`` 再与配置文件、函数预设合并。

同包多入口时用 ``cli=`` 指定：``cli=cartopy`` 会找
``{包名}_cartopy_cli.py`` / ``cartopy_cli.py`` 等。

数字前缀包（如 ``00_blend``）若 ``{包名}_cli.py`` 不可作
Python 模块名，则用下表别名或去掉前缀数字后的 ``{stem}_cli.py``。

在 ``00temp`` 目录::

    python -m frequency_matching_rain24
    python -m utils.nimm_cli frequency_matching_rain24 pro_count=1
    python -m utils.nimm_cli 00_blend
    python -m coordinate_projection_transform cli=cartopy mode=lonlat-to-equal source_cube=...
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Optional

from utils.merge_params import parse_kv_argv


_TEMP_ROOT = Path(__file__).resolve().parents[1]
_UTILS_DIR = Path(__file__).resolve().parent

# 包目录名 → cli 文件主干（不含 .py）；用于数字前缀等非法模块名
_CLI_STEM_ALIASES = {
    "00_blend": "00_blend_cli",
}


def _pairs(argv):
    """把 ``模块名`` 和 ``key=value`` 收成关键字参数。"""

    return parse_kv_argv(argv, bare_as_module=True)


def _cli_stem(module: str) -> str:
    if module in _CLI_STEM_ALIASES:
        return _CLI_STEM_ALIASES[module]
    return f"{module}_cli"


def _resolve_cli_file(module: str, cli: Optional[str] = None) -> Path:
    """定位 ``cli`` 入口文件。

    ``cli`` 可选：短名（如 ``cartopy``）或完整主干（如
    ``coordinate_projection_transform_cartopy_cli``）。
    """
    root = _TEMP_ROOT / module
    cli_dir = root / "cli"
    if cli:
        name = str(cli).strip()
        if name.endswith(".py"):
            name = name[:-3]
        stems = []
        if name.endswith("_cli"):
            stems.append(name)
        else:
            stems.extend(
                [
                    name,
                    f"{name}_cli",
                    f"{module}_{name}_cli",
                ]
            )
            stripped = re.sub(r"^\d+_", "", module)
            if stripped != module:
                stems.append(f"{stripped}_{name}_cli")
        seen = set()
        for stem in stems:
            if stem in seen:
                continue
            seen.add(stem)
            path = cli_dir / f"{stem}.py"
            if path.is_file():
                return path
        raise FileNotFoundError(
            f"没有找到入口 cli={cli!r}，已试: "
            + ", ".join(f"{s}.py" for s in stems)
        )

    candidates = [
        cli_dir / f"{_cli_stem(module)}.py",
        cli_dir / f"{module}_cli.py",
    ]
    stripped = re.sub(r"^\d+_", "", module)
    if stripped != module:
        candidates.append(cli_dir / f"{stripped}_cli.py")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"没有找到入口: {cli_dir / f'{module}_cli.py'}（亦无别名 {_cli_stem(module)}.py）"
    )


def _prepare_sys_path(root: Path) -> None:
    existing = sys.modules.get("cli")
    existing_file = getattr(existing, "__file__", None) if existing is not None else None
    if existing_file and root not in Path(existing_file).resolve().parents:
        for key in list(sys.modules):
            if key == "cli" or key.startswith("cli."):
                del sys.modules[key]
    root_s = str(root)
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)
    utils_mod = sys.modules.get("utils")
    if utils_mod is not None and Path(getattr(utils_mod, "__file__", "") or "").resolve() == (_UTILS_DIR / "__init__.py").resolve():
        path = list(utils_mod.__path__)
        for item in (root / "utils", _UTILS_DIR, root / "src" / "utils"):
            if item.is_dir() and str(item.resolve()) not in path:
                path.append(str(item.resolve()))
        utils_mod.__path__ = path


def _load(module: str, cli: Optional[str] = None):
    """导入包内 cli 入口；非法标识符时按文件加载。"""
    root = _TEMP_ROOT / module
    cli_file = _resolve_cli_file(module, cli=cli)
    _prepare_sys_path(root)
    stem = cli_file.stem
    dotted = f"cli.{stem}"
    if stem.isidentifier():
        return importlib.import_module(dotted)
    # 如 00_blend_cli：不能作属性名，按路径加载
    mod_name = f"_nimm_cli_{module.replace('.', '_')}_{stem}"
    spec = importlib.util.spec_from_file_location(mod_name, cli_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载入口: {cli_file}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _import_process(module, cli: Optional[str] = None):
    """取出该模块的 ``process``。模块级函数优先，否则用类上的 ``process``。"""
    cli_module = _load(module, cli=cli)
    process = getattr(cli_module, "process", None)
    if callable(process):
        return process
    for obj in vars(cli_module).values():
        if not isinstance(obj, type):
            continue
        process = getattr(obj, "process", None)
        wrapped = getattr(process, "__func__", None)
        if getattr(wrapped, "__nimm_merge_params__", False):
            return process
    raise LookupError(f"{cli_module.__name__} 没有可调用的 process")


def _print_modules():
    names = []
    extras = []
    for path in sorted(_TEMP_ROOT.glob("*/cli/*_cli.py")):
        module = path.parent.parent.name
        stem = path.stem
        expected = _cli_stem(module)
        stripped_stem = "%s_cli" % re.sub(r"^\d+_", "", module)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "@merge_params" not in text:
            continue
        if stem in (expected, f"{module}_cli", stripped_stem):
            names.append(module)
        else:
            # 同包次入口：显示为 包名  cli=短名
            short = stem
            prefix = f"{module}_"
            if short.startswith(prefix) and short.endswith("_cli"):
                short = short[len(prefix) : -4]
            elif short.endswith("_cli"):
                short = short[:-4]
            extras.append(f"{module}  cli={short}")
    # 别名包即使主文件名不同也列入
    for module, stem in _CLI_STEM_ALIASES.items():
        path = _TEMP_ROOT / module / "cli" / f"{stem}.py"
        if module not in names and path.is_file() and "@merge_params" in path.read_text(encoding="utf-8"):
            names.append(module)
    names = sorted(set(names))
    print("用法: python -m utils.nimm_cli <模块名> [cli=次入口] [key=value ...]")
    print("已挂 @merge_params 的子模块:")
    print("\n".join(f"  {name}" for name in names) if names else "  (无)")
    if extras:
        print("同包次入口（加 cli=）:")
        print("\n".join(f"  {item}" for item in extras))


def nimm_cli(argv=None):
    """命令行入口。第一项不是 ``key=value`` 时当作模块名。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] in (["-h"], ["--help"]) or not args:
        _print_modules()
        return 0
    try:
        params = _pairs(args)
        module = params.pop("module", None)
        if not module:
            _print_modules()
            return 0
        cli = params.pop("cli", None) or params.pop("entry", None)
        process = _import_process(module, cli=cli)
        previous = Path.cwd()
        os.chdir(_TEMP_ROOT / module / "cli")
        try:
            process(**params)
        finally:
            os.chdir(previous)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    temp = str(_TEMP_ROOT)
    if temp not in sys.path:
        sys.path.insert(0, temp)
    raise SystemExit(nimm_cli())
