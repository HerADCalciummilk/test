"""把 l2-review.json 渲染成审核评论中「LLM审核」一节的 Markdown。

只输出该节正文，不含 SHA 标题、提交、算法包、Actions（这些在整条评论顶部已有）。

典型调用：
  python format_l2_comment.py --json l2-review.json --out l2-review-comment.md
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rules import COMMENT_MARKER_L2

BEIJING = ZoneInfo("Asia/Shanghai")

RISK_LABEL = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _fmt_finding(item: dict) -> list[str]:
    """单条 LLM 发现：严重度、类别、标题、路径、详情与依据。"""
    lines: list[str] = []
    sev = item.get("severity") or "low"
    title = (item.get("title") or "").strip() or "(无标题)"
    loc = (item.get("path") or "").strip()
    cat = item.get("category") or "other"
    head = f"- **[{RISK_LABEL.get(sev, sev)}]** ({cat}) {title}"
    if loc:
        head += f" — `{loc}`"
    lines.append(head)
    detail = (item.get("detail") or "").replace("\n", " ").strip()
    if detail:
        if len(detail) > 200:
            detail = detail[:197] + "..."
        lines.append(f"  - {detail}")
    evidence = (item.get("evidence") or "").replace("\n", " ").strip()
    if evidence:
        if len(evidence) > 160:
            evidence = evidence[:157] + "..."
        lines.append(f"  - 依据：{evidence}")
    return lines


def render_markdown(
    report: dict,
    *,
    run_url: str = "",
    sha: str = "",
    checked_at: str = "",
) -> str:
    """渲染 LLM审核节正文。sha / run_url 保留以兼容旧调用，不写入正文。"""
    del run_url, sha
    summary = report.get("summary") or {}
    findings = report.get("findings") or []
    risk = summary.get("risk_level") or report.get("risk_level") or "low"
    skipped = bool(report.get("skipped"))

    if skipped:
        status = f"已跳过（{report.get('skip_reason') or '见报告'}）"
    elif risk == "high":
        status = "总体风险高（见发现项；不阻断合并）"
    elif findings:
        status = "有发现（不阻断合并）"
    else:
        status = "未见明显语义风险"

    checked_at = checked_at or datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S %z")

    lines = [
        COMMENT_MARKER_L2,
        f"**结果**：{status}",
        f"**完成时间**：{checked_at}",
        f"**风险**：{RISK_LABEL.get(str(risk), str(risk))}",
        f"**发现数**：{int(summary.get('finding_count') or len(findings))}",
        f"**模型**：`{report.get('model') or '—'}`",
        "",
    ]

    overview = (report.get("overview") or "").strip()
    if overview:
        lines.extend(["#### 总评", "", overview, ""])

    if report.get("error"):
        lines.extend(["#### 错误", "", f"```\n{report['error']}\n```", ""])

    if findings:
        lines.append("#### 发现项")
        lines.append("")
        shown = 0
        for item in findings:
            if shown >= 20:
                lines.append(f"- … 另有 {len(findings) - shown} 条，详见 Artifact `l2-review.json`")
                break
            lines.extend(_fmt_finding(item))
            shown += 1
        lines.append("")

    if not findings and not overview and not skipped:
        lines.extend(["模型未返回有效内容。", ""])

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染 LLM审核节（写入整条评论的占位）")
    parser.add_argument("--json", default="l2-review.json")
    parser.add_argument("--out", default="l2-review-comment.md")
    parser.add_argument("--run-url", default="", help="已忽略（兼容旧调用）")
    parser.add_argument("--sha", default="", help="已忽略（兼容旧调用）")
    parser.add_argument("--attempt", type=int, default=1, help="已忽略（兼容旧调用）")
    parser.add_argument("--checked-at", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.json).read_text(encoding="utf-8"))
    run_url = args.run_url or os.environ.get("GITHUB_RUN_URL", "")
    sha = args.sha or os.environ.get("GITHUB_SHA", "")
    text = render_markdown(
        report,
        run_url=run_url,
        sha=sha,
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
