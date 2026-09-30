"""将静态/动态结果与 LLM 输出写成「总评 + 分项」两部分的 Markdown / JSON。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import DEP_TOTAL_WARN_THRESHOLD
from .models import Finding, ReviewReport

SECTION_TITLES = {
    "structure": "目录结构",
    "syntax": "语法",
    "plugins": "插件形态",
    "flake8": "flake8",
    "docstrings": "注释",
    "dependencies": "依赖完整性",
    "meb_grid": "meb 数据格式",
    "execution": "pytest 运行",
}

SEVERITY_ORDER = {"blocker": 0, "warning": 1, "info": 2}
SEVERITY_BADGE = {"blocker": "阻断", "warning": "警告", "info": "信息"}

# LLM 必填字段 meb_verdict.verdict 的中文呈现
MEB_VERDICT_TEXT = {
    "yes": "符合 meb 数据格式",
    "partial": "部分符合",
    "no": "不符合",
    "unclear": "无法判定",
}


def _short_path(path: str, package_id: str) -> str:
    """路径相对包根显示：审单个包时，仓库前缀每行都一样，纯属噪音。

    JSON 里仍是仓库相对路径，便于外部工具定位。
    """
    path = (path or "").strip()
    if not package_id:
        return path
    if path == package_id:
        return "整包"
    prefix = package_id + "/"
    return path[len(prefix):] if path.startswith(prefix) else path


def _short_msg(message: str, package_id: str) -> str:
    """消息正文里内嵌的路径同样去掉包前缀。

    各检查模块会把文件路径拼进句子（如「证据来自 …」），统一在渲染层剥离，
    省得每个模块各自处理。
    """
    if not package_id or not message:
        return message
    return message.replace(package_id + "/", "")


def _fmt_finding_cn(f: Finding, package_id: str = "") -> str:
    badge = SEVERITY_BADGE.get(f.severity, f.severity)
    loc = _short_path(f.path, package_id)
    if f.line:
        loc = f"{loc}:{f.line}"
    return f"- **[{badge}]** `{loc}` — {_short_msg(f.message, package_id)}"


def _strip_llm_duplicate_headings(body: str) -> str:
    """去掉模型正文里与模板重复的「概述 / 静态…」大段，保留语义与建议。"""
    text = body.strip()
    for pattern in (
        r"^##\s*概述\s*\n.*?(?=^##\s)",
        r"^##\s*总评\s*\n.*?(?=^##\s)",
        r"^##\s*静态与动态检查结果\s*\n.*?(?=^##\s)",
        r"^##\s*静态检查[^\n]*\n.*?(?=^##\s)",
    ):
        text = re.sub(pattern, "", text, count=1, flags=re.MULTILINE | re.DOTALL)
    return text.strip()


def _section_by_name(report: ReviewReport, name: str):
    for sec in report.sections:
        if sec.name == name:
            return sec
    return None


def _missing_docstring_count(report: ReviewReport) -> int | None:
    sec = _section_by_name(report, "docstrings")
    if sec is None or sec.skipped:
        return None
    value = (sec.metrics or {}).get("missing_docstring")
    return int(value) if isinstance(value, int) else None


def _pytest_state(report: ReviewReport) -> str:
    sec = _section_by_name(report, "execution")
    if sec is None:
        return "未执行"
    if sec.skipped:
        return f"已跳过（{sec.skip_reason}）"
    runs = (sec.metrics or {}).get("runs") or []
    for run in runs:
        if run.get("kind") == "pytest":
            code = run.get("exit_code")
            if code == 0:
                return f"通过（{run.get('elapsed_sec')}s）"
            return f"失败（exit={code}）"
    for f in sec.findings:
        if f.severity == "blocker":
            return f"未通过：{f.message}"
    return "未执行"


def _overview_block(report: ReviewReport, llm: dict[str, Any]) -> list[str]:
    summary = report.to_dict()["summary"]
    infos = sum(1 for f in report.all_findings() if f.severity == "info")
    missing_doc = _missing_docstring_count(report)

    rows = [
        f"| 算法包 | `{report.package_id}` |",
        f"| 检查时间 | {report.generated_at_text()} |",
        f"| 机器发现 | 阻断 **{summary['blocker_count']}** · "
        f"警告 **{summary['warning_count']}** · 信息 **{infos}** |",
    ]
    if missing_doc is not None:
        rows.append(f"| 注释 | 共 **{missing_doc}** 处缺 docstring |")
    dep = _section_by_name(report, "dependencies")
    if dep is not None and not dep.skipped:
        m = dep.metrics or {}
        declared = m.get("declared_count", 0)
        too_many = "，偏多" if declared > DEP_TOTAL_WARN_THRESHOLD else ""
        bits = [f"声明 **{declared}** 个{too_many}"]
        undeclared = m.get("undeclared") or []
        conflicts = m.get("conflicts") or []
        bits.append(
            f"未声明 **{len(undeclared)}** 个" if undeclared else "import 已全部声明"
        )
        if conflicts:
            bits.append(f"版本冲突 **{len(conflicts)}** 处")
        rows.append("| 依赖 | " + " · ".join(bits) + " |")
    rows.append(f"| pytest | {_pytest_state(report)} |")
    if llm.get("skipped"):
        rows.append(f"| LLM | 未执行（{llm.get('skip_reason', '')}） |")
    else:
        rows.append(f"| 模型 | `{llm.get('model', '')}` |")
        if llm.get("risk_level"):
            rows.append(f"| 风险等级 | `{llm.get('risk_level')}` |")
        meb = _meb_verdict(llm)
        if meb is not None:
            verdict = str(meb.get("verdict") or "unclear")
            issues = meb.get("issues")
            extra = (
                f"，{len(issues)} 处问题"
                if isinstance(issues, list) and issues
                else ""
            )
            rows.append(
                f"| meb 格式 | {MEB_VERDICT_TEXT.get(verdict, verdict)}{extra} |"
            )
        else:
            rows.append("| meb 格式 | LLM 未给出判定 |")

    lines = [
        "## 一、总评",
        "",
        "| 项目 | 内容 |",
        "|------|------|",
        *rows,
        "",
    ]
    overview = (llm.get("overview") or "").strip()
    if overview:
        lines.extend([overview, ""])
    elif llm.get("skipped"):
        lines.extend(["_未调用 LLM，仅机器检查结果。_", ""])
    return lines


FLAKE8_LINE_LIMIT = 10


def _flake8_md(findings: list[Finding], package_id: str) -> list[str]:
    """flake8 按「文件 + 错误码」合并。

    同一文件里十几个 E262 对应的是同一个动作（改注释前缀），逐条列出只会
    把别的检查项挤下去；行号仍全部保留，不丢定位信息。
    """
    groups: dict[tuple[str, str, str], list[int]] = {}
    order: list[tuple[str, str, str]] = []
    for f in findings:
        code, _, text = (f.message or "").partition(" ")
        key = (_short_path(f.path, package_id), code, text.strip())
        if key not in groups:
            groups[key] = []
            order.append(key)
        if f.line:
            groups[key].append(f.line)

    lines: list[str] = []
    # 同文件内按出现次数降序：数量多的更值得先动手
    for path, code, text in sorted(
        order, key=lambda k: (k[0], -len(groups[k]), k[1])
    ):
        nums = sorted(groups[(path, code, text)])
        shown = "、".join(str(n) for n in nums[:FLAKE8_LINE_LIMIT])
        if len(nums) > FLAKE8_LINE_LIMIT:
            shown += f" 等 {len(nums)} 处"
        where = f"（行 {shown}）" if nums else ""
        count = f" ×{len(nums)}" if len(nums) > 1 else ""
        lines.append(f"- **[警告]** `{path}` — {code} {text}{count}{where}")
    return lines


def _machine_summary_sections(report: ReviewReport) -> list[str]:
    """分项：按检查逐节列出发现（脚本生成，不与 LLM 叙述重复）。"""
    lines: list[str] = []

    for sec in report.sections:
        if sec.name == "execution":
            continue  # 运行记录单独渲染
        title = SECTION_TITLES.get(sec.name, sec.name)
        lines.append(f"### {title}")
        lines.append("")
        if sec.skipped:
            lines.append(f"_已跳过：{sec.skip_reason}_")
            lines.append("")
            continue
        findings = sorted(
            sec.findings,
            key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.path),
        )
        if sec.name == "dependencies":
            # 依赖一节即使没问题也交代清楚比对基准
            metrics = sec.metrics or {}
            imports = metrics.get("third_party_imports") or []
            files = metrics.get("manifests") or []
            pythons = metrics.get("python_requires") or []
            source = (
                "、".join(f"`{_short_path(p, report.package_id)}`" for p in files)
                if files
                else "无依赖清单"
            )
            constraint = "　版本约束：全部缺失（环境无法复现）" if metrics.get(
                "unconstrained"
            ) else ""
            py_text = "、".join(f"`{p}`" for p in pythons) or "未声明"
            py_files = metrics.get("python_version_files") or []
            if py_files:
                # 这两个文件不是打包标准，标注来源以免误认为正式声明
                py_text += (
                    "（含 "
                    + "、".join(
                        f"`{_short_path(p, report.package_id)}`" for p in py_files
                    )
                    + "）"
                )
            lines.append(
                f"清单：{source}　代码用到 **{len(imports)}** 个外部库"
                f"　Python 版本要求：{py_text}{constraint}"
            )
            lines.append("")
        if not findings:
            lines.append("- 通过（无发现项）")
            lines.append("")
            continue
        if sec.name == "docstrings":
            count = (sec.metrics or {}).get("missing_docstring")
            if isinstance(count, int):
                lines.append(f"共 **{count}** 处缺 docstring：")
                lines.append("")
        if sec.name == "flake8":
            lines.extend(_flake8_md(findings, report.package_id))
        else:
            for f in findings:
                lines.append(_fmt_finding_cn(f, report.package_id))
        lines.append("")
    return lines


def _render_execution_md(report: ReviewReport) -> list[str]:
    sec = _section_by_name(report, "execution")
    if sec is None:
        return []
    lines = [f"### {SECTION_TITLES['execution']}", ""]
    if sec.skipped:
        lines.extend([f"_已跳过：{sec.skip_reason}_", ""])
        return lines

    metrics = sec.metrics or {}
    lines.extend(_execution_env_md(metrics))
    runs = metrics.get("runs") or []
    for run in runs:
        code = run.get("exit_code")
        status = "通过" if code == 0 else f"失败（exit={code}）"
        lines.append(f"- **结果**：{status}　**耗时**：`{run.get('elapsed_sec')}s`")
        log_tail = (run.get("log_tail") or "").strip()
        if log_tail:
            short = "\n".join(log_tail.splitlines()[-8:])
            lines.append("- **日志**：")
            lines.append("")
            lines.append("```text")
            lines.append(short)
            lines.append("```")
        lines.append("")
    if not runs:
        for f in sorted(
            sec.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9)
        ):
            lines.append(_fmt_finding_cn(f))
        lines.append("")
    return lines


def _execution_env_md(metrics: dict[str, Any]) -> list[str]:
    """运行环境说明；venv 路径只在保留时才给（删掉了就没有参考价值）。"""
    env = metrics.get("env") or {}
    bits: list[str] = []
    if env.get("python"):
        bits.append(f"Python `{env['python']}`")
    if env.get("pytest"):
        bits.append(f"pytest `{env['pytest']}`")
    if env.get("platform"):
        bits.append(f"`{env['platform']}`")
    if metrics.get("site_packages") == "inherited":
        bits.append("继承本机库")
    elif metrics.get("site_packages") == "isolated":
        bits.append("全隔离环境")
    req = metrics.get("requirements")
    if req:
        bits.append(f"已装 `{Path(req).name}`")
    elif metrics.get("venv"):
        bits.append("包内无 requirements.txt")

    disposition = metrics.get("venv_disposition")
    if disposition == "removed":
        bits.append("临时 venv（跑完已删除）")
    elif disposition == "reuse":
        bits.append(f"复用 venv `{metrics.get('venv', '')}`")
    elif disposition == "kept":
        bits.append(f"保留 venv `{metrics.get('venv', '')}`")
    elif disposition == "cleanup_failed":
        bits.append(f"venv 未能删除 `{metrics.get('venv', '')}`")

    if not bits:
        return []
    lines = [f"- **环境**：{' · '.join(bits)}"]
    required = metrics.get("required_libs") or {}
    if required:
        label = {
            "present": "已就绪",
            "installed": "本轮安装",
            "install_failed": "安装失败",
            "missing": "缺失",
        }
        lines.append(
            "- **必需库**："
            + " · ".join(
                f"{name} {label.get(state, state)}"
                for name, state in required.items()
            )
        )
    libs = env.get("libs") or {}
    if libs:
        detail = " · ".join(f"{name} `{ver}`" for name, ver in sorted(libs.items()))
        lines.append(f"- **可用依赖**：{detail}")
    elif metrics.get("venv"):
        lines.append("- **可用依赖**：未检测到常见科学计算库（numpy / xarray / meb 等）")
    lines.append("")
    return lines


def _meb_verdict(llm: dict[str, Any]) -> dict[str, Any] | None:
    v = llm.get("meb_verdict")
    return v if isinstance(v, dict) else None


def _meb_verdict_md(llm: dict[str, Any]) -> list[str]:
    """LLM 的 meb 格式判定单独成节，避免被语义要点淹没。"""
    lines = ["### meb 数据格式（LLM 复核）", ""]
    data = _meb_verdict(llm)
    if data is None:
        # 必填字段缺失时把缺口显式写出来，不静默跳过
        lines.extend(["_LLM 未按要求给出 meb 判定，请以静态证据为准。_", ""])
        return lines

    verdict = str(data.get("verdict") or "unclear")
    lines.append(f"**结论**：{MEB_VERDICT_TEXT.get(verdict, verdict)}")
    lines.append("")
    for label, key in (("入参", "input"), ("出参", "output")):
        text = str(data.get(key) or "").strip()
        if text:
            lines.append(f"- **{label}**：{text}")
    basis = str(data.get("basis") or "").strip()
    if basis:
        lines.append(f"- **依据**：{basis}")
    issues = data.get("issues")
    if isinstance(issues, list) and issues:
        lines.append("- **问题**：")
        lines.extend(f"  - {str(x).strip()}" for x in issues if str(x).strip())
    lines.append("")
    return lines


def _llm_findings_md(llm: dict[str, Any], package_id: str = "") -> list[str]:
    findings = llm.get("findings")
    if not isinstance(findings, list) or not findings:
        return []
    lines = ["### 语义审查要点", ""]
    for i, item in enumerate(findings, 1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "发现"
        path = _short_path(str(item.get("path") or ""), package_id)
        meta = " · ".join(
            x
            for x in (
                item.get("severity") or "",
                item.get("category") or "",
                f"`{path}`" if path else "",
            )
            if x
        )
        head = f"{i}. **{title}**"
        if meta:
            head += f"（{meta}）"
        lines.append(head)
        if item.get("detail"):
            lines.append(f"   {item['detail']}")
        if item.get("evidence"):
            lines.append(f"   - 依据：{item['evidence']}")
        lines.append("")
    return lines


def _llm_body_md(llm: dict[str, Any]) -> list[str]:
    body = llm.get("markdown_body")
    if not isinstance(body, str) or not body.strip():
        return []
    text = _strip_llm_duplicate_headings(body)
    if not text:
        return []
    # 模型正文里的二级标题降为三级，保持「总-分」两层骨架
    text = re.sub(r"^##\s+", "### ", text, flags=re.MULTILINE)
    if not text.lstrip().startswith("###"):
        return ["### 补充说明与建议", "", text, ""]
    return [text, ""]


def render_markdown(report: ReviewReport) -> str:
    llm = report.llm or {}
    parts: list[str] = [f"# 本地检查报告：`{report.package_id}`", ""]
    parts.extend(_overview_block(report, llm))
    parts.extend(["## 二、分项检查", ""])
    parts.extend(_machine_summary_sections(report))
    parts.extend(_render_execution_md(report))
    if not llm.get("skipped"):
        parts.extend(_meb_verdict_md(llm))
        parts.extend(_llm_findings_md(llm, report.package_id))
        parts.extend(_llm_body_md(llm))
    return "\n".join(parts).rstrip() + "\n"


def write_outputs(
    report: ReviewReport,
    *,
    json_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
