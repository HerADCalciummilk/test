"""把 l2-review.json 渲染成 PR 评论 Markdown。

与 format_l1_comment.py 并列：独立 marker、独立模板；评论发布流程可复用。

典型调用：
  python format_l2_comment.py --json l2-review.json --out l2-review-comment.md \\
    --sha $GITHUB_SHA --run-url $GITHUB_RUN_URL --attempt N
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


def now_beijing_text() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S %z")


def _fmt_finding(item: dict) -> list[str]:
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
    attempt: int = 1,
    checked_at: str = "",
) -> str:
    summary = report.get("summary") or {}
    findings = report.get("findings") or []
    packages = report.get("packages") or []
    risk = summary.get("risk_level") or report.get("risk_level") or "low"
    skipped = bool(report.get("skipped"))

    if skipped:
        status = f"已跳过（{report.get('skip_reason') or '见报告'}）"
    elif risk == "high":
        status = "总体风险高（见发现项；不阻断合并）"
    elif findings:
        status = "有发现（advisory，不阻断合并）"
    else:
        status = "未见明显语义风险"

    checked_at = checked_at or now_beijing_text()

    lines = [
        COMMENT_MARKER_L2,
        f"## L2 LLM 审核结果（第 {attempt} 次）",
        "",
        f"**状态**：{status}",
        f"**检查时间**：{checked_at}",
        f"**门禁**：`{report.get('gate', 'l2')}`（advisory）",
        f"**风险等级**：{RISK_LABEL.get(str(risk), str(risk))}",
        f"**算法包**：{', '.join(f'`{p}`' for p in packages) if packages else '（无）'}",
        f"**发现数**：{int(summary.get('finding_count') or len(findings))}",
        f"**模型**：`{report.get('model') or '—'}`",
    ]
    if sha:
        lines.append(f"**提交**：`{sha[:12]}`")
    if run_url:
        lines.append(f"**Actions 运行**：[查看日志与 Artifact]({run_url})")

    lines.extend(["", "---", ""])

    overview = (report.get("overview") or "").strip()
    if overview:
        lines.extend(["### 总评", "", overview, ""])

    if report.get("error"):
        lines.extend(["### 错误", "", f"```\n{report['error']}\n```", ""])

    if findings:
        lines.append("### 发现项")
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

    lines.extend(
        [
            "<details><summary>说明</summary>",
            "",
            "- L2 为 **LLM 辅助评审**，默认**不阻断**合并；人工以发现项（含严重度）为准。",
            "- 在 Create PR 或新 push 时追加评论；Re-run 不发评论。",
            "- 完整报告见 Artifact：`l2-review-report-<run_id>` / `l2-review.json`。",
            "- 需配置 Secrets：`OPENAI_API_KEY`；可选 `OPENAI_BASE_URL`、`OPENAI_MODEL`。",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染 L2 PR 评论")
    parser.add_argument("--json", default="l2-review.json")
    parser.add_argument("--out", default="l2-review-comment.md")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--sha", default="")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--checked-at", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = json.loads(Path(args.json).read_text(encoding="utf-8"))
    run_url = args.run_url or os.environ.get("GITHUB_RUN_URL", "")
    sha = args.sha or os.environ.get("GITHUB_SHA", "")
    attempt = args.attempt if args.attempt >= 1 else 1
    text = render_markdown(
        report,
        run_url=run_url,
        sha=sha,
        attempt=attempt,
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
