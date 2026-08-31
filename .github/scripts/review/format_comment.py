"""把 review.json 渲染成 PR 评论 Markdown（本目录三件套之一：评论）。

职责：读取 L1 检查产出的 JSON，生成带时间戳、「第 N 次」的 Markdown。
workflow 每次检查会追加一条新评论（不覆盖历史），便于按时间线回溯。

典型调用（CI）：
  python format_comment.py --json review.json --out review-comment.md \\
    --sha $GITHUB_SHA --run-url $GITHUB_RUN_URL --attempt N
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from rules import COMMENT_MARKER, RULES

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


def now_beijing_text() -> str:
    """检查时间展示用：北京时间，含时区偏移。"""
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S %z")


def render_markdown(
    report: dict,
    *,
    run_url: str = "",
    sha: str = "",
    attempt: int = 1,
    checked_at: str = "",
) -> str:
    """由 review.json 结构生成完整评论正文。

    文首 COMMENT_MARKER 供 workflow 统计本 PR 已有多少条 L1 评论。
    阻断/警告列表过长时截断，完整内容以 Artifact 为准。
    """
    summary = report.get("summary") or {}
    blockers = report.get("blockers") or []
    warnings = report.get("warnings") or []
    packages = report.get("packages") or []

    blocker_n = int(summary.get("blocker_count") or len(blockers))
    warning_n = int(summary.get("warning_count") or len(warnings))

    if blocker_n:
        status = "未通过（存在阻断项）"
    elif warning_n:
        status = "通过（有警告，建议修复）"
    else:
        status = "通过"

    checked_at = checked_at or now_beijing_text()

    lines = [
        COMMENT_MARKER,
        f"## L1 机器审核结果（第 {attempt} 次）",
        "",
        f"**状态**：{status}",
        f"**检查时间**：{checked_at}",
        f"**门禁**：`{report.get('gate', 'l1')}`",
        f"**算法包**：{', '.join(f'`{p}`' for p in packages) if packages else '（本次变更未识别到算法包）'}",
        f"**阻断**：{blocker_n}　**警告**：{warning_n}",
    ]
    # 提交 = git commit SHA；Actions 链接对应该次 run（含 Artifact）
    if sha:
        lines.append(f"**提交**：`{sha[:12]}`")
    if run_url:
        lines.append(f"**Actions 运行**：[查看日志与 Artifact]({run_url})")

    lines.extend(["", "---", ""])

    if blockers:
        lines.append("### 阻断项（须修复）")
        lines.append("")
        shown = 0
        for item in blockers:
            if shown >= 20:
                lines.append(f"- … 另有 {len(blockers) - shown} 条，详见 Artifact `review.json`")
                break
            lines.extend(_fmt_finding(item))
            shown += 1
        lines.append("")

    if warnings:
        lines.append("### 警告项（建议修复）")
        lines.append("")
        shown = 0
        for item in warnings:
            if shown >= 20:
                lines.append(f"- … 另有 {len(warnings) - shown} 条，详见 Artifact `review.json`")
                break
            lines.extend(_fmt_finding(item))
            shown += 1
        lines.append("")

    if not blockers and not warnings:
        lines.extend(["未发现问题。", ""])

    lines.extend(
        [
            "<details><summary>说明</summary>",
            "",
            "- 在 **Create PR**（opened）或向 PR **新 push**（synchronize）时追加评论；Re-run 不发评论。",
            "- 完整 JSON 报告在该次 Actions 的 Artifact：`l1-review-report-<run_id>` / `review.json`（随该次运行保留）。",
            "- 阻断项会导致检查失败；警告不单独阻断合并。",
            "",
            "</details>",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染 L1 PR 评论")
    parser.add_argument("--json", default="review.json", help="review.json 路径")
    parser.add_argument("--out", default="review-comment.md", help="Markdown 输出路径")
    parser.add_argument("--run-url", default="", help="Actions run URL")
    parser.add_argument("--sha", default="", help="提交 SHA")
    parser.add_argument("--attempt", type=int, default=1, help="本 PR 第几次 L1 检查")
    parser.add_argument("--checked-at", default="", help="检查时间（默认当前北京时间）")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = Path(args.json)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    run_url = args.run_url or os.environ.get("GITHUB_RUN_URL", "")
    sha = args.sha or os.environ.get("GITHUB_SHA", "")
    attempt = args.attempt
    if attempt < 1:
        attempt = int(os.environ.get("L1_ATTEMPT", "1") or "1")
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
