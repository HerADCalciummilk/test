"""meb 数据格式检查（静态）。

判不了运行时真实类型，所以采的是可复核的静态证据，从强到弱：

1. 类型注解与 isinstance 守卫里的 `xr.DataArray` / `pandas.DataFrame`；
2. 时空坐标指纹：网格维名（member/level/time/dtime/lat/lon）或站点固定列
   （level/time/dtime/id/lat/lon）成组出现；
3. `meb.*` 里含 griddata/stadata 的调用；
4. 网格必备 attrs（units/model/dtime_units/level_type/time_type/time_bounds）
   与参数命名提示——都只作补充，算法代码里直接碰 attrs 的地方本就不多。

结论只答一个问题：入参出参**是不是 meb 数据格式**。网格与站点仅作附注，
不影响判定，也不为区分二者引入额外规则。实际逻辑是否真按规范走交 LLM 复核。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    MEB_API_NAMES,
    MEB_API_SUBSTRINGS,
    MEB_FINGERPRINT_MIN_HITS,
    MEB_GRID_ANNOTATIONS,
    MEB_GRID_ATTR_MIN_HITS,
    MEB_GRID_ATTR_NAMES,
    MEB_GRID_DIM_NAMES,
    MEB_MODULE_NAMES,
    MEB_NAME_HINTS,
    MEB_STATION_ANNOTATIONS,
    MEB_STATION_COLUMNS,
    SKIP_DIR_NAMES,
)
from .models import Finding, SectionResult
from .package import PackageRef, read_text, repo_rel


@dataclass
class Signals:
    """一段代码（模块或单个方法）里采到的 meb 相关证据。"""

    imports: set[str] = field(default_factory=set)
    apis: set[str] = field(default_factory=set)
    name_hints: set[str] = field(default_factory=set)
    grid_types: set[str] = field(default_factory=set)  # 注解/isinstance 命中网格类型
    station_types: set[str] = field(default_factory=set)
    plain_array: bool = False  # 注解里同时允许 ndarray/list 等非 meb 类型
    words: set[str] = field(default_factory=set)  # 字符串字面量与关键字名，供指纹匹配

    def merge(self, other: "Signals") -> None:
        self.imports |= other.imports
        self.apis |= other.apis
        self.name_hints |= other.name_hints
        self.grid_types |= other.grid_types
        self.station_types |= other.station_types
        self.plain_array = self.plain_array or other.plain_array
        self.words |= other.words

    def grid_dim_hits(self) -> int:
        return sum(1 for name in MEB_GRID_DIM_NAMES if name in self.words)

    def grid_attr_hits(self) -> int:
        """按槽位计数：同一属性的多种写法只算一次。"""
        return sum(
            1
            for aliases in MEB_GRID_ATTR_NAMES
            if any(name in self.words for name in aliases)
        )

    def station_column_hits(self) -> int:
        return sum(1 for name in MEB_STATION_COLUMNS if name in self.words)

    def has_fingerprint(self) -> bool:
        """时空坐标指纹。

        `dtime`（预报时效）是 meb 特有的轴名，要求它在场可挡掉普通
        经纬度数据的误判；网格维名与站点列名共用一套阈值，不区分二者。
        """
        hits = max(self.grid_dim_hits(), self.station_column_hits())
        return hits >= MEB_FINGERPRINT_MIN_HITS and "dtime" in self.words

    def has_meb_evidence(self) -> bool:
        return bool(
            self.grid_types
            or self.apis
            or self.has_fingerprint()
            or self.grid_attr_hits() >= MEB_GRID_ATTR_MIN_HITS
        )

    def shape_hint(self) -> str:
        """附注：看着更像网格还是站点，不参与判定。"""
        # member 只在这个附注里用来区分两种形态，不参与「是否 meb 格式」的判定
        grid = bool(self.grid_types) or (
            self.grid_dim_hits() >= MEB_FINGERPRINT_MIN_HITS and "member" in self.words
        )
        station = (
            bool(self.station_types)
            and self.station_column_hits() >= MEB_FINGERPRINT_MIN_HITS
        )
        if grid and station:
            return "网格与站点"
        if station:
            return "站点表"
        if grid:
            return "网格"
        return ""


def _annotation_names(node: ast.AST | None) -> set[str]:
    """取注解里出现的所有类型名（含 Union/| 的各分支）。"""
    names: set[str] = set()
    if node is None:
        return names
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            names.add(sub.value.split(".")[-1])  # 字符串注解 "xr.DataArray"
    return names


def _classify_annotation(names: set[str], sig: Signals) -> None:
    for name in names:
        if name in MEB_GRID_ANNOTATIONS:
            sig.grid_types.add(name)
        elif name in MEB_STATION_ANNOTATIONS:
            sig.station_types.add(name)
        elif name in ("ndarray", "array", "list", "tuple", "float", "int"):
            sig.plain_array = True


def _is_meb_api(func: ast.AST) -> str | None:
    """判断调用是否为 meb 数据操作，返回命中的函数名。"""
    name = getattr(func, "attr", None) or getattr(func, "id", None)
    if not name:
        return None
    if name in MEB_API_NAMES:
        return name
    lower = name.lower()
    if any(part in lower for part in MEB_API_SUBSTRINGS):
        return name  # 含 griddata/stadata 的调用（含包内 helper）
    return None


def _collect_meb_signals(tree: ast.AST) -> Signals:
    """从 AST 采集 meb 证据。"""
    sig = Signals()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] in MEB_MODULE_NAMES:
                    sig.imports.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".", 1)[0]
            if mod in MEB_MODULE_NAMES:
                sig.imports.add(mod)
                for alias in node.names:
                    if alias.name in MEB_API_NAMES:
                        sig.apis.add(alias.name)
        elif isinstance(node, ast.Call):
            api = _is_meb_api(node.func)
            if api:
                sig.apis.add(api)
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id in MEB_MODULE_NAMES:
                    sig.imports.add(func.value.id)
            # isinstance(x, xr.DataArray) 与注解等价的类型证据
            if isinstance(func, ast.Name) and func.id == "isinstance":
                for arg in node.args[1:]:
                    _classify_annotation(_annotation_names(arg), sig)
            for kw in node.keywords:
                if kw.arg:
                    sig.words.add(kw.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = list(node.args.args) + list(node.args.kwonlyargs)
            for arg in args:
                _classify_annotation(_annotation_names(arg.annotation), sig)
                low = arg.arg.lower()
                for hint in MEB_NAME_HINTS:
                    if hint in low:
                        sig.name_hints.add(arg.arg)
            _classify_annotation(_annotation_names(node.returns), sig)
            for name in _annotation_names(node.returns):
                if any(h in name.lower() for h in MEB_NAME_HINTS):
                    sig.name_hints.add(name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            sig.words.add(node.value)

    return sig


def _process_methods(
    node: ast.ClassDef,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """具体插件（有基类）的 process 才算算法入口。

    基类里的 `def process(self, data): return data` 是待实现的桩，
    拿它判数据格式只会制造假警报。
    """
    if not node.bases:
        return []
    return [
        item
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "process"
    ]


def _scan_targets(root: Path, package: PackageRef) -> list[tuple[Path, bool]]:
    """待扫文件与是否属于源码根。

    源码根内的文件才做 process 逐个判定；包内 utils/cli 等只贡献格式证据。
    测试目录排除：测试夹具造网格不代表算法本身按 meb 走。
    """
    src = package.source_dir(root).resolve()
    test_dir = package.test_dir(root).resolve()
    roots = {src, package.package_root(root).resolve(), package.cli_dir(root).resolve()}

    targets: dict[Path, bool] = {}
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved.is_relative_to(test_dir):
                continue
            in_src = resolved.is_relative_to(src)
            targets[resolved] = targets.get(resolved, False) or in_src
    return sorted(targets.items())


def _process_verdict(own: Signals, module: Signals) -> tuple[str, str]:
    """单个 process 是否按 meb 数据格式收发，以及依据。"""
    if own.grid_types or own.station_types:
        return "meb", f"入参/返回注解含 {sorted(own.grid_types | own.station_types)}"
    if own.apis:
        return "meb", f"方法内调用 {sorted(own.apis)}"
    if own.has_fingerprint():
        return "meb", "方法内出现 meb 时空坐标（含 dtime）"
    if own.grid_attr_hits() >= MEB_GRID_ATTR_MIN_HITS:
        return "meb", "方法内读写网格必备 attrs"
    if own.name_hints:
        return "meb", f"参数命名提示 {sorted(own.name_hints)}"
    if module.imports and module.apis:
        return "weak", "模块级 import meb 并调用 meb 数据接口，但方法内无直接信号"
    return "none", "方法内外均未见 meb 数据格式信号"


def check_meb_grid(root: Path, package: PackageRef, *, required: bool) -> SectionResult:
    """静态判断入参出参是否走 meb 网格/站点格式。"""
    section = SectionResult(name="meb_grid")
    if not required:
        section.skipped = True
        section.skip_reason = "清单声明 meb_grid_required=false"
        section.metrics["meb_grid_required"] = False
        return section

    src = package.source_dir(root)
    if not src.is_dir():
        section.skipped = True
        section.skip_reason = "源码根不存在"
        return section

    total = Signals()
    process_entries: list[dict[str, str]] = []
    optional_inputs: list[str] = []
    aux_evidence: list[str] = []

    for path, is_src in _scan_targets(root, package):
        text = read_text(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue

        module_sig = _collect_meb_signals(tree)
        total.merge(module_sig)
        rel = repo_rel(root, path)
        if not is_src:
            # 网格构造/还原常写在 utils、cli 里，指纹与接口证据一并采信
            if module_sig.has_meb_evidence():
                aux_evidence.append(rel)
            continue

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for proc in _process_methods(node):
                own = _collect_meb_signals(proc)
                verdict, reason = _process_verdict(own, module_sig)
                where = f"{rel}:{node.name}.process"
                process_entries.append(
                    {"where": where, "verdict": verdict, "reason": reason, "line": str(proc.lineno)}
                )
                if own.plain_array and (own.grid_types or own.station_types):
                    optional_inputs.append(where)

    grid_hits = total.grid_dim_hits()
    attr_hits = total.grid_attr_hits()
    station_hits = total.station_column_hits()
    verdicts = {e["verdict"] for e in process_entries}
    if "meb" in verdicts or total.has_meb_evidence():
        io_kind = "meb"
    elif "weak" in verdicts:
        io_kind = "meb_weak"
    else:
        io_kind = "unknown"

    section.metrics = {
        "meb_grid_required": True,
        "io_kind": io_kind,
        "shape_hint": total.shape_hint(),
        "meb_imports": sorted(total.imports),
        "meb_apis_seen": sorted(total.apis),
        "grid_annotations": sorted(total.grid_types),
        "station_annotations": sorted(total.station_types),
        "grid_dim_hits": f"{grid_hits}/{len(MEB_GRID_DIM_NAMES)}",
        "grid_attr_hits": f"{attr_hits}/{len(MEB_GRID_ATTR_NAMES)}",
        "station_column_hits": f"{station_hits}/{len(MEB_STATION_COLUMNS)}",
        "name_hints": sorted(total.name_hints),
        "process_total": len(process_entries),
        "process_entries": process_entries[:20],
        "accepts_plain_array": sorted(set(optional_inputs)),
        "evidence_outside_src": sorted(set(aux_evidence))[:10],
    }

    _emit_meb_findings(
        section,
        root=root,
        package=package,
        total=total,
        io_kind=io_kind,
        process_entries=process_entries,
        optional_inputs=sorted(set(optional_inputs)),
        aux_evidence=sorted(set(aux_evidence)),
    )
    return section


def _emit_meb_findings(
    section: SectionResult,
    *,
    root: Path,
    package: PackageRef,
    total: Signals,
    io_kind: str,
    process_entries: list[dict[str, str]],
    optional_inputs: list[str],
    aux_evidence: list[str],
) -> None:
    add = section.findings.append
    src_rel = repo_rel(root, package.source_dir(root))

    if io_kind == "unknown":
        add(
            Finding(
                rule_id="MEB_GRID_NOT_USED",
                severity="warning",
                path=src_rel,
                message=(
                    "未检测到 meb 数据格式的任何信号（无 meb 导入/接口调用，"
                    "注解中无 xr.DataArray / pandas.DataFrame，也未见 meb 时空坐标）；"
                    "算法入参出参应采用 meb 数据格式"
                ),
                evidence="static heuristic",
            )
        )
        return

    unclear = [e for e in process_entries if e["verdict"] in ("none", "weak")]
    if unclear:
        first = unclear[0]
        add(
            Finding(
                rule_id="MEB_GRID_PROCESS_UNCLEAR",
                severity="warning",
                path=first["where"].split(":")[0],
                line=int(first["line"]) if first["line"].isdigit() else None,
                message=(
                    f"{len(unclear)} 个 process 自身看不出入参出参是否为 meb 数据格式："
                    + "；".join(f"{e['where']}（{e['reason']}）" for e in unclear[:5])
                ),
                evidence=", ".join(e["where"] for e in unclear[:5]),
            )
        )

    if optional_inputs:
        add(
            Finding(
                rule_id="MEB_GRID_OPTIONAL_INPUT",
                severity="info",
                path=optional_inputs[0].split(":")[0],
                message=(
                    "入口同时接受裸数组等非 meb 类型（"
                    + "、".join(optional_inputs[:5])
                    + "）：并非强制 meb 数据格式，请确认是否符合规范"
                ),
            )
        )

    kind_text = (
        "符合 meb 数据格式"
        if io_kind == "meb"
        else "疑似 meb 数据格式（仅模块级信号，未落到 process 内）"
    )
    shape = total.shape_hint()
    if shape:
        kind_text += f"，看着是{shape}"
    bits = []
    if total.grid_types or total.station_types:
        bits.append(f"注解 {sorted(total.grid_types | total.station_types)}")
    if total.apis:
        bits.append(f"接口 {sorted(total.apis)[:5]}")
    if total.imports:
        bits.append(f"导入 {sorted(total.imports)}")
    if total.has_fingerprint():
        hits = max(total.grid_dim_hits(), total.station_column_hits())
        bits.append(f"时空坐标 {hits}/6")
    if total.grid_attr_hits() >= MEB_GRID_ATTR_MIN_HITS:
        bits.append(f"网格 attrs {total.grid_attr_hits()}/6")
    if aux_evidence:
        bits.append("源码根外证据来自 " + "、".join(aux_evidence[:3]))
    add(
        Finding(
            rule_id="MEB_GRID_SIGNAL_OK",
            severity="info",
            path=src_rel,
            message=f"入参出参{kind_text}；依据：{'；'.join(bits) or '无'}",
            evidence="static heuristic",
        )
    )
