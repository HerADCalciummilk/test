"""把 l1-review.json 渲染成 PR 评论 Markdown。

同一提交 SHA 对应一条审核评论：共用一个标题，正文分「静态检查」与「LLM审核」两节。
LLM审核先占位，完成后更新占位。不再使用「第 N 次」，评论里不写 L1/L2。

典型调用（CI）：
  python format_l1_comment.py --json l1-review.json --out l1-review-comment.md \\
    --sha $HEAD_SHA --run-url $GITHUB_RUN_URL --l2-status pending
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rules import (
    COMMENT_MARKER_L1,
    L2_SLOT_END,
    L2_SLOT_START,
    RULES,
    review_round_marker,
)

BEIJING = ZoneInfo("Asia/Shanghai")


def _fmt_finding(item: dict) -> list[str]:
    """单条发现格式化为评论中的列表项（含规则标题与位置）。"""
    lines: list[str] = []
    rule = RULES.get(item["rule_id"])
    title = rule.title if rule else item["rule_id"]
    loc = item["path"]
    if item.get("line"):
        loc = f"{loc}:{item['line']}"
    msg = (item.get("message") or "").replace("\n", " ").strip()
    if len(msg) > 120:
        msg = msg[:117] + "..."
    lines.append(f"- **{item['rule_id']}** ({title}) — `{loc}`")
    if msg:
        lines.append(f"  - {msg}")
    return lines


def render_markdown(
    report: dict,
    *,
    run_url: str = "",
    sha: str = "",
    l2_status: str = "pending",
    checked_at: str = "",
) -> str:
    """由 l1-review.json 生成整条审核评论（含 LLM审核占位）。"""
    summary = report.get("summary") or {}
    blockers = report.get("blockers") or []
    warnings = report.get("warnings") or []
    packages = report.get("packages") or []

    blocker_n = int(summary.get("blocker_count") or len(blockers))
    warning_n = int(summary.get("warning_count") or len(warnings))

    if blocker_n:
        status = "未通过（存在阻断项）"
        l2_status = "skipped"
    elif warning_n:
        status = "通过（有警告，建议修复）"
    else:
        status = "通过"

    if l2_status not in {"pending", "skipped"}:
        l2_status = "pending"

    checked_at = checked_at or datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S %z")
    short = sha[:12] if sha else "—"
    pkg_text = ", ".join(f"`{p}`" for p in packages) if packages else "（本次变更未识别到算法包）"

    lines = [
        review_round_marker(sha) if sha else COMMENT_MARKER_L1,
        f"## 审核 `{short}`",  # 评论内用二级标题；一级 # 在 PR 时间线上过大
        "",
        f"- **提交**：`{sha or '—'}`",
        f"- **算法包**：{pkg_text}",
        f"- **检查时间**：{checked_at}",
    ]
    if run_url:
        lines.append(f"- **Actions 运行**：[查看日志与 Artifact]({run_url})")

    lines.extend(
        [
            "",
            "---",
            "",
            COMMENT_MARKER_L1,
            "### 静态检查",
            "",
            f"**结果**：{status}",
            f"**阻断**：{blocker_n}　**警告**：{warning_n}",
            "",
        ]
    )

    if blockers:
        lines.append("#### 阻断项（须修复）")
        lines.append("")
        shown = 0
        for item in blockers:
            if shown >= 20:
                lines.append(f"- … 另有 {len(blockers) - shown} 条，详见 Artifact `l1-review.json`")
                break
            lines.extend(_fmt_finding(item))
            shown += 1
        lines.append("")

    if warnings:
        lines.append("#### 警告项（建议修复）")
        lines.append("")
        shown = 0
        for item in warnings:
            if shown >= 20:
                lines.append(f"- … 另有 {len(warnings) - shown} 条，详见 Artifact `l1-review.json`")
                break
            lines.extend(_fmt_finding(item))
            shown += 1
        lines.append("")

    if not blockers and not warnings:
        lines.extend(["未发现问题。", ""])

    inner = "未执行（静态检查未通过）。" if l2_status == "skipped" else "进行中，完成后此段会更新。"
    lines.extend(
        [
            "---",
            "",
            "### LLM审核",
            "",
            L2_SLOT_START,
            "",
            inner,
            "",
            L2_SLOT_END,
            "",
            "<details><summary>说明</summary>",
            "",
            "- 同一提交一条评论：静态检查先发出，LLM审核完成后更新本条；静态检查未通过则不跑 LLM审核。",
            "- 完整 JSON 在 Artifact：`l1-review-report-<run_id>` / `l2-review-report-<run_id>`。",
            "- 阻断项会导致静态检查失败；警告不单独阻断合并。LLM审核为辅助评审，默认不阻断。",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染审核 PR 评论（含 LLM审核占位）")
    parser.add_argument("--json", default="l1-review.json", help="l1-review.json 路径")
    parser.add_argument("--out", default="l1-review-comment.md", help="Markdown 输出路径")
    parser.add_argument("--run-url", default="", help="Actions run URL")
    parser.add_argument("--sha", default="", help="PR head SHA（一轮检查的 ID）")
    parser.add_argument(
        "--l2-status",
        choices=("pending", "skipped"),
        default="pending",
        help="pending：LLM审核进行中；skipped：静态检查未通过",
    )
    parser.add_argument("--attempt", type=int, default=1, help="已忽略（兼容旧调用）")
    parser.add_argument("--checked-at", default="", help="检查时间（默认当前北京时间）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.json)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    run_url = args.run_url or os.environ.get("GITHUB_RUN_URL", "")
    sha = args.sha or os.environ.get("GITHUB_SHA", "")
    text = render_markdown(
        report,
        run_url=run_url,
        sha=sha,
        l2_status=args.l2_status,
        checked_at=args.checked_at,
    )
    out = Path(args.out)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n已写入 {out.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    import sys

    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    raise SystemExit(main())
