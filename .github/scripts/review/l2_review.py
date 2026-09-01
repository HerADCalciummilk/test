"""L2 LLM 语义审核入口。

职责：定位算法包 → 收集 docs + 源码 + cli 文本上下文（可选附带 L1 报告）→
调用 OpenAI 兼容 Chat Completions → 写出结构化 l2-review.json。

典型调用：
  python l2_review.py --base <base_sha> --json l2-review.json
  python l2_review.py --path 00temp/demo_algo_clean --json l2-review.json
  python l2_review.py --path 00temp/demo_algo_clean --dry-run --json l2-review.json

环境变量：
  OPENAI_API_KEY   必填（非 dry-run）
  OPENAI_BASE_URL  可选，默认 https://api.openai.com/v1
  OPENAI_MODEL     可选，默认 gpt-4o-mini

退出码：0 正常（含跳过）；1 配置/调用失败（workflow 可选择是否红灯）。
L2 发现本身默认不阻断合并（advisory）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from common import (
    PackageRef,
    changed_paths,
    discover_packages,
    iter_files,
    mid_has_entry_dirs,
    read_text,
    repo_rel,
    resolve_path_arg,
)
from rules import MAX_TEXT_FILE_BYTES

# 单文件 / 总上下文上限，控制 token
MAX_FILE_CHARS = 12_000
MAX_TOTAL_CHARS = 60_000
DOC_SUFFIXES = {".md", ".txt", ".rst"}
CODE_SUFFIXES = {".py"}

SYSTEM_PROMPT = """你是算法仓库的 L2 代码审核助手（辅助人工，不替代机器门禁与人工终审）。
根据给定的算法包源码与文档，做**尽量全面**的语义与工程意图评审。
不要重复罗列 L1 已能用规则判定的事项（缺目录、缺 __init__/process、flake8 风格等），除非对理解风险有必要一笔带过。

核查范围（有依据再写，覆盖你能看到的 docs / 源码 / cli）：
1. 算法/插件逻辑是否像真实业务实现（含 process 是否空壳、无关转发）
2. **cli 是否真正调用插件业务**：应实例化具体插件（或等价调度）并调用 process（或约定主入口）；仅 print/占位、未调用则必须写入 findings
3. 与 docs 描述、参数/数据含义、命名与领域概念是否大致一致
4. 可疑点：硬编码业务假设、隐蔽 I/O、不安全执行、明显不合理的科学/工程做法、明显遗漏或易错处
5. 其它你认为入库前应让人知道的问题

输出必须是**仅含一个 JSON 对象**的文本（不要 Markdown 围栏），schema：
{
  "risk_level": "low" | "medium" | "high",
  "overview": "一两句中文总评",
  "findings": [
    {
      "severity": "low" | "medium" | "high",
      "category": "semantics" | "docs" | "security" | "cli" | "other",
      "path": "相对路径或类名，未知则空字符串",
      "title": "短标题",
      "detail": "说明",
      "evidence": "引用或依据（可短）"
    }
  ]
}
字段约定：
- findings = 发现的问题（带严重度）；人工据此逐条处理即可（可按 severity 优先看 high）
- risk_level = 本趟总体风险（综合 findings）
- 不要输出 needs_human_attention、human_checklist
若信息不足，risk_level 用 low，在 overview 说明局限，findings 可为空。
对 cli：有可读 cli 文件时必须明确「有调用插件业务 / 无调用并写入 findings」。
正式包的 cli 在仓库根级 cli/<kind>/<pkg>/，不要求 NIMM 包内再套 cli。
若上下文是「非算法包变更文件」（如 NIMM/utils、CI 脚本等）：不做六树/整包假设，按给定文件做语义与风险核查即可。
"""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n...[truncated]...\n"


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _path_covered_by_packages(repo: Path, path: Path, packages: list[PackageRef]) -> bool:
    for pkg in packages:
        for root in pkg.iter_scan_roots(repo):
            if _is_under(path, root):
                return True
    return False


def collect_changed_files_context(repo: Path, files: list[Path], *, title: str) -> str:
    """无包或包外变更：把可读变更文件拼成 LLM 上下文。"""
    chunks: list[str] = [
        f"## {title}\n",
        "说明：以下为本次变更中的可读文件（非完整算法包上下文）。"
        "请做语义/风险核查；若无 cli/插件则不要臆造包结构问题。\n",
    ]
    used = 0
    candidates = [p for p in files if p.is_file()]

    def sort_key(p: Path) -> tuple[int, str]:
        rel = repo_rel(repo, p)
        if rel.startswith("NIMM/utils") or "/utils/" in f"/{rel}/":
            pri = 0
        elif p.suffix == ".py":
            pri = 1
        elif p.suffix.lower() in DOC_SUFFIXES:
            pri = 2
        else:
            pri = 3
        return (pri, rel)

    for path in sorted(candidates, key=sort_key):
        suffix = path.suffix.lower()
        if suffix not in DOC_SUFFIXES and suffix not in CODE_SUFFIXES:
            continue
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        text = read_text(path)
        if text is None:
            continue
        rel = repo_rel(repo, path)
        piece = _truncate(text, MAX_FILE_CHARS)
        block = f"### 文件 `{rel}`\n```\n{piece}\n```\n"
        if used + len(block) > MAX_TOTAL_CHARS:
            chunks.append("\n（其余文件因长度上限已省略）\n")
            break
        chunks.append(block)
        used += len(block)

    if used == 0:
        chunks.append("（未采集到可读变更文本）\n")
    return "\n".join(chunks)


def collect_package_context(repo: Path, package: PackageRef) -> str:
    """收集算法包 docs + 源码 + cli 文本。

    - 中间：包内 docs / src / cli
    - 正式：docs/<kind>/<pkg>、NIMM/<kind>/<pkg>、cli/<kind>/<pkg>
    """
    if package.layout == "official":
        cli_hint = f"`cli/{package.kind}/{package.pkg}/`"
        layout_note = "正式分散树：源码在 NIMM，cli/docs 在仓库根级对应路径。"
    else:
        cli_hint = "`cli/`"
        layout_note = "中间目录：docs/src/cli 均在包内。"

    chunks: list[str] = [
        f"## 算法包 `{package.package_id}`（{package.layout}）\n",
        f"说明：{layout_note} 请尽量全面核查；并特别核对 {cli_hint} 是否实例化插件并调用 "
        "`process`（或等价业务主入口）。仅占位/print、未调用插件业务时必须写入 findings。\n",
    ]
    used = 0

    docs_dir = package.docs_dir(repo)
    src_dir = package.source_dir(repo)
    cli_dir = package.cli_dir(repo)

    candidates: list[Path] = []
    for d in (docs_dir, src_dir, cli_dir):
        if d.is_dir():
            candidates.extend(iter_files(d))

    def sort_key(p: Path) -> tuple[int, str]:
        rel = repo_rel(repo, p)
        if docs_dir.is_dir() and _is_under(p, docs_dir):
            pri = 0
        elif src_dir.is_dir() and _is_under(p, src_dir):
            pri = 1
        else:
            pri = 2
        return (pri, rel)

    for path in sorted(candidates, key=sort_key):
        suffix = path.suffix.lower()
        if suffix not in DOC_SUFFIXES and suffix not in CODE_SUFFIXES:
            continue
        if path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        text = read_text(path)
        if text is None:
            continue
        rel = repo_rel(repo, path)
        piece = _truncate(text, MAX_FILE_CHARS)
        block = f"### 文件 `{rel}`\n```\n{piece}\n```\n"
        if used + len(block) > MAX_TOTAL_CHARS:
            chunks.append("\n（其余文件因长度上限已省略）\n")
            break
        chunks.append(block)
        used += len(block)

    if used == 0:
        chunks.append("（未采集到可读的 docs/源码/cli 文本）\n")
    return "\n".join(chunks)


def load_l1_summary(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    summary = data.get("summary") or {}
    lines = [
        "## L1 机器审核摘要（供参考，勿简单重复）",
        f"- packages: {data.get('packages')}",
        f"- blockers: {summary.get('blocker_count')}",
        f"- warnings: {summary.get('warning_count')}",
    ]
    for key in ("blockers", "warnings"):
        items = data.get(key) or []
        for item in items[:15]:
            lines.append(
                f"- [{item.get('severity')}] {item.get('rule_id')} @ {item.get('path')}: "
                f"{(item.get('message') or '')[:100]}"
            )
    return "\n".join(lines) + "\n"


def build_user_prompt(contexts: list[str], l1_summary: str) -> str:
    parts = ["请评审下列算法包内容，并按 system 要求输出 JSON。\n"]
    if l1_summary:
        parts.append(l1_summary)
    parts.extend(contexts)
    return "\n".join(parts)


def _extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出中取出 JSON 对象（容忍偶发 Markdown 围栏）。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def call_chat_completions(
    *,
    api_key: str,
    base_url: str,
    model: str,
    user_prompt: str,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], str]:
    """调用 OpenAI 兼容接口；返回 (解析后的 JSON, 原始 content)。"""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 openai 包，请 pip install openai") from exc

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        timeout=timeout,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("模型返回空内容")
    return _extract_json_object(content), content


def normalize_model_result(raw: dict[str, Any]) -> dict[str, Any]:
    risk = str(raw.get("risk_level") or "low").lower()
    if risk not in {"low", "medium", "high"}:
        risk = "low"
    findings_in = raw.get("findings") or []
    findings: list[dict[str, Any]] = []
    for item in findings_in:
        if not isinstance(item, dict):
            continue
        sev = str(item.get("severity") or "low").lower()
        if sev not in {"low", "medium", "high"}:
            sev = "low"
        cat = str(item.get("category") or "other").lower()
        if cat not in {"semantics", "docs", "security", "cli", "other"}:
            cat = "other"
        findings.append(
            {
                "severity": sev,
                "category": cat,
                "path": str(item.get("path") or ""),
                "title": str(item.get("title") or ""),
                "detail": str(item.get("detail") or ""),
                "evidence": str(item.get("evidence") or ""),
            }
        )
    return {
        "risk_level": risk,
        "overview": str(raw.get("overview") or ""),
        "findings": findings,
    }


def dry_run_result(packages: list[str]) -> dict[str, Any]:
    return {
        "risk_level": "low",
        "overview": "dry-run：未调用 LLM，仅验证流水线与报告格式。",
        "findings": [],
        "packages_note": packages,
    }


def build_report(
    packages: list[str],
    *,
    model: str,
    skipped: bool,
    skip_reason: str | None,
    result: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    result = result or {}
    findings = result.get("findings") or []
    return {
        "gate": "l2",
        "packages": packages,
        "model": model,
        "skipped": skipped,
        "skip_reason": skip_reason,
        "error": error,
        "summary": {
            "risk_level": result.get("risk_level") or "low",
            "finding_count": len(findings),
        },
        "overview": result.get("overview") or "",
        "findings": findings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NIMM L2 LLM 算法审核")
    parser.add_argument("--repo-root", default=".", help="仓库根目录")
    parser.add_argument("--base", default="", help="git diff 基准")
    parser.add_argument("--path", action="append", default=[], help="算法包路径，可重复")
    parser.add_argument("--json", default="l2-review.json", help="报告输出路径")
    parser.add_argument("--l1-json", default="", help="可选：附带 L1 l1-review.json 摘要")
    parser.add_argument("--dry-run", action="store_true", help="不调用 LLM，写出占位报告")
    parser.add_argument("--model", default="", help="覆盖 OPENAI_MODEL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo_root).resolve()

    packages: list[PackageRef] = []
    changed_rels: list[Path] = []

    if args.path:
        for raw in args.path:
            ref = resolve_path_arg(repo, raw)
            if ref is not None:
                if ref.layout == "mid" and not mid_has_entry_dirs(repo, ref):
                    continue
                packages.append(ref)
                continue
            # --path 未识别为包：当作文件/目录纳入变更上下文（如 NIMM/utils）
            target = repo / raw
            if target.is_file():
                changed_rels.append(Path(raw))
            elif target.is_dir():
                for path in iter_files(target):
                    changed_rels.append(Path(repo_rel(repo, path)))
    elif args.base:
        changed_rels = changed_paths(repo, args.base)
        packages = discover_packages(repo, changed_rels)

    package_strs = [p.package_id for p in packages]
    model = args.model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    api_key = os.environ.get("OPENAI_API_KEY") or ""

    out = Path(args.json)
    if not out.is_absolute():
        out = repo / out

    l1_path = Path(args.l1_json) if args.l1_json else None
    if l1_path and not l1_path.is_absolute():
        l1_path = repo / l1_path

    # 包外变更（含仅改 NIMM/utils、文档、脚本等）
    orphan_files: list[Path] = []
    for rel in changed_rels:
        abs_path = repo / rel if not rel.is_absolute() else rel
        if not abs_path.is_file():
            continue
        if packages and _path_covered_by_packages(repo, abs_path, packages):
            continue
        orphan_files.append(abs_path)

    contexts: list[str] = []
    if packages:
        contexts.extend(collect_package_context(repo, pkg) for pkg in packages)
    if orphan_files:
        title = (
            "非算法包变更文件（如 NIMM/utils 或仓库其它路径）"
            if packages
            else "本次变更文件（未识别到算法包）"
        )
        contexts.append(collect_changed_files_context(repo, orphan_files, title=title))

    has_llm_input = bool(packages) or bool(orphan_files)

    if not has_llm_input:
        report = build_report(
            package_strs,
            model=model,
            skipped=True,
            skip_reason="无算法包且无变更可读文件，跳过 LLM",
            result={
                "risk_level": "low",
                "overview": "本次无算法包、也无可用变更文件，未调用 LLM。",
                "findings": [],
            },
        )
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"L2 跳过：无审核输入 report={out}")
        return 0

    if args.dry_run:
        result = normalize_model_result(dry_run_result(package_strs or ["(changed-files)"]))
        report = build_report(
            package_strs,
            model="dry-run",
            skipped=False,
            skip_reason=None,
            result=result,
        )
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"L2 dry-run 完成：packages={package_strs or '无'} "
            f"orphan_files={len(orphan_files)} report={out}"
        )
        return 0

    if not api_key:
        report = build_report(
            package_strs,
            model=model,
            skipped=True,
            skip_reason="未配置 OPENAI_API_KEY",
            result={
                "risk_level": "low",
                "overview": "未配置 OPENAI_API_KEY，L2 未执行。请在仓库 Secrets 中配置后重跑。",
                "findings": [],
            },
        )
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"L2 跳过：无 API Key report={out}")
        return 1

    user_prompt = build_user_prompt(contexts, load_l1_summary(l1_path))

    try:
        raw, _ = call_chat_completions(
            api_key=api_key,
            base_url=base_url,
            model=model,
            user_prompt=user_prompt,
        )
        result = normalize_model_result(raw)
        report = build_report(
            package_strs,
            model=model,
            skipped=False,
            skip_reason=None,
            result=result,
        )
        exit_code = 0
    except Exception as exc:  # noqa: BLE001 — 统一写入报告
        report = build_report(
            package_strs,
            model=model,
            skipped=True,
            skip_reason="LLM 调用或解析失败",
            result={
                "risk_level": "low",
                "overview": "L2 调用失败，请查看 Actions 日志。",
                "findings": [],
            },
            error=str(exc),
        )
        exit_code = 1
        print(f"L2 失败：{exc}", file=sys.stderr)

    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"L2 完成：packages={package_strs or '无'} "
        f"orphan_files={len(orphan_files)} "
        f"risk={report['summary']['risk_level']} "
        f"findings={report['summary']['finding_count']} "
        f"skipped={report['skipped']} report={out}"
    )
    return exit_code


if __name__ == "__main__":
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    raise SystemExit(main())
