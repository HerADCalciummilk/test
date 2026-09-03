"""把正式 PR 上的代码改动摘要写到已关联的需求 Issue。

不新建 Issue、不改 Issue 正文/勾选、不复制 L1/L2。
草稿 PR 不写评论。无关联则跳过。无 API Key 时降级为路径列表。

典型调用（CI）：
  python issue_sync.py --pr 12 --action opened --head <sha> --base <sha>
  python issue_sync.py --pr 12 --action synchronize --head <sha> --before <sha>
  python issue_sync.py --pr 12 --action edited --head <sha> --base <sha>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMMENT_MARKER = "<!-- nimm-issue-sync -->"
MAX_DIFF_CHARS = 40_000
MAX_PATHS = 20
USER_AGENT = "nimm-issue-sync"

# GitHub 关闭关键字（不含 Refs / Related）
_CLOSING_KW = r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)"
_CLOSE_HASH = re.compile(
    rf"(?:^|[^\w]){_CLOSING_KW}\s+(?:[\w.-]+/[\w.-]+#|#)(\d+)\b",
    re.IGNORECASE,
)
_CLOSE_URL = re.compile(
    rf"(?:^|[^\w]){_CLOSING_KW}\s+https://github\.com/[^/\s]+/[^/\s]+/issues/(\d+)\b",
    re.IGNORECASE,
)

PROGRESS_SYSTEM = """你为算法仓库的需求 Issue 写「这一次代码改了什么」，不是审核、不是发版 notes。
根据 diff 用中文写 3～6 句：改了哪些与需求相关的点。
可以提「可能对应 Issue 中的某一步」，但不要宣称目标或验收已完成。
不要评价代码质量，不要提 L1/L2，不要猜测 diff 中未出现的需求。
不要使用 Markdown 标题。输出纯文本段落即可。
"""

GQL_CLOSING = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      closingIssuesReferences(first: 50) {
        nodes { number }
      }
    }
  }
}
"""


def repo_root() -> Path:
    return Path(os.environ.get("GITHUB_WORKSPACE") or Path.cwd())


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_closing_issue_numbers(text: str) -> set[int]:
    """从 PR 描述解析 Fixes/Closes/Resolves #n，忽略 Refs。"""
    found: set[int] = set()
    blob = text or ""
    for match in _CLOSE_HASH.finditer(blob):
        found.add(int(match.group(1)))
    for match in _CLOSE_URL.finditer(blob):
        found.add(int(match.group(1)))
    return found


def newly_linked_issues(current: set[int], previous: set[int]) -> set[int]:
    return set(current) - set(previous)


def issues_to_comment(action: str, current: set[int], previous: set[int]) -> set[int]:
    if action == "edited":
        return newly_linked_issues(current, previous)
    return set(current)


def should_skip_draft(draft: bool) -> bool:
    return bool(draft)


def sha_marker(sha: str) -> str:
    return f"<!-- sha:{sha} -->"


def already_synced(comments: list[dict[str, Any]], sha: str) -> bool:
    needle = sha_marker(sha)
    for item in comments:
        body = item.get("body") or ""
        if COMMENT_MARKER in body and needle in body:
            return True
    return False


def fallback_summary(paths: list[str], hint: str) -> str:
    shown = paths[:MAX_PATHS]
    extra = len(paths) - len(shown)
    path_part = "、".join(f"`{p}`" for p in shown) if shown else "（无路径信息）"
    if extra > 0:
        path_part += f" 等 {len(paths)} 个文件"
    hint = (hint or "").strip()
    if hint:
        return f"{hint}。涉及：{path_part}。"
    if len(paths) == 1:
        return f"修改了 {path_part}。"
    return f"修改了 {path_part}。"


def _path_bullets(paths: list[str]) -> list[str]:
    shown = paths[:MAX_PATHS]
    lines = [f"- `{p}`" for p in shown]
    extra = len(paths) - len(shown)
    if extra > 0:
        lines.append(f"- … 另有 {extra} 个文件")
    if not lines:
        lines.append("- （无）")
    return lines


def format_progress_time(when: datetime | None = None) -> str:
    stamp = when or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc)
    return stamp.strftime("%Y-%m-%d %H:%M UTC")


def format_progress_comment(
    *,
    pr_number: int,
    sha: str,
    paths: list[str],
    summary: str,
    scope: str,
    when: datetime | None = None,
) -> str:
    heading = (
        "相对 base 的当前改动"
        if scope == "full"
        else "这一推"
    )
    return "\n".join(
        [
            COMMENT_MARKER,
            sha_marker(sha),
            f"<!-- pr:{pr_number} -->",
            f"## PR #{pr_number}（{heading}）",
            "",
            f"- 时间：{format_progress_time(when)}",
            f"- 提交：`{sha[:12]}`",
            "- 路径：",
            *_path_bullets(paths),
            "",
            "### 改了什么",
            summary.strip(),
            "",
            "目标和验收请在本 Issue 中人工勾选；本评论不更新清单，也不含 L1/L2 结论。",
            "",
        ]
    )


def comment_scope(action: str) -> str:
    if action in {"opened", "ready_for_review", "edited"}:
        return "full"
    return "push"


def changed_paths(before: str, after: str, cwd: Path) -> list[str]:
    result = run_git(
        ["diff", "--name-only", "--diff-filter=ACMRD", before, after, "--"],
        cwd,
    )
    if result.returncode != 0:
        print(result.stderr or "git diff 失败", file=sys.stderr)
        return []
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def unified_diff(before: str, after: str, cwd: Path) -> str:
    result = run_git(["diff", before, after, "--"], cwd)
    text = result.stdout or ""
    if len(text) > MAX_DIFF_CHARS:
        return text[: MAX_DIFF_CHARS - 20] + "\n\n...[truncated]...\n"
    return text


def commit_hint(before: str, after: str, cwd: Path) -> str:
    result = run_git(["log", "--format=%s", f"{before}..{after}"], cwd)
    if result.returncode != 0:
        return ""
    messages = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return "；".join(messages[:8])


def _headers(token: str, *, json_body: bool = False, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    if extra:
        headers.update(extra)
    return headers


def _api(
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    url = f"https://api.github.com{path}"
    data = None
    headers = _headers(token, json_body=payload is not None, extra=extra_headers)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {path} -> {exc.code}: {body}") from exc


def graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=data,
        method="POST",
        headers=_headers(token, json_body=True),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL -> {exc.code}: {body}") from exc
    if raw.get("errors") and not raw.get("data"):
        raise RuntimeError(f"GitHub GraphQL errors: {raw['errors']}")
    return raw.get("data") or {}


def linked_from_graphql(owner: str, repo: str, token: str, pr_number: int) -> set[int]:
    try:
        data = graphql(
            token,
            GQL_CLOSING,
            {"owner": owner, "name": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        print(f"GraphQL 关联 Issue 失败，仅用描述解析：{exc}", file=sys.stderr)
        return set()
    nodes = (
        (((data.get("repository") or {}).get("pullRequest") or {})
         .get("closingIssuesReferences") or {})
        .get("nodes")
        or []
    )
    found: set[int] = set()
    for node in nodes:
        number = node.get("number")
        if number is not None:
            found.add(int(number))
    return found


def linked_from_timeline(owner: str, repo: str, token: str, pr_number: int) -> set[int]:
    """Development 栏「已连接」但未写 Fixes 时，closingIssuesReferences 可能为空。"""
    found: set[int] = set()
    try:
        items = _api(
            "GET",
            f"/repos/{owner}/{repo}/issues/{pr_number}/timeline?per_page=100",
            token,
            extra_headers={"Accept": "application/vnd.github+json"},
        ) or []
    except RuntimeError as exc:
        print(f"读取 PR timeline 失败：{exc}", file=sys.stderr)
        return found
    connected: set[int] = set()
    disconnected: set[int] = set()
    if not isinstance(items, list):
        return found
    for event in items:
        kind = event.get("event")
        source = event.get("source") or {}
        issue = source.get("issue") or source
        number = issue.get("number") if isinstance(issue, dict) else None
        if number is None:
            continue
        n = int(number)
        if kind == "connected":
            connected.add(n)
        elif kind == "disconnected":
            disconnected.add(n)
    return connected - disconnected


def list_comments(owner: str, repo: str, token: str, issue_number: int) -> list[dict[str, Any]]:
    items = _api(
        "GET",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100",
        token,
    ) or []
    return items if isinstance(items, list) else []


def post_comment(owner: str, repo: str, token: str, issue_number: int, body: str) -> None:
    _api(
        "POST",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        token,
        {"body": body},
    )


def summarize_with_llm(*, paths: list[str], diff: str, hint: str) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        print("未安装 openai，使用路径降级摘要", file=sys.stderr)
        return None

    model = os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    base_url = os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    user = (
        f"提交说明/PR 标题（可能为空）：{hint or '（无）'}\n"
        f"变更路径：\n" + "\n".join(paths[:80]) + "\n\n"
        f"diff：\n{diff or '（无 diff）'}\n"
    )
    try:
        client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": PROGRESS_SYSTEM},
                {"role": "user", "content": user},
            ],
            timeout=90.0,
        )
        content = (response.choices[0].message.content or "").strip()
        return content or None
    except Exception as exc:  # noqa: BLE001
        print(f"LLM 摘要失败，降级：{exc}", file=sys.stderr)
        return None


def resolve_diff_range(action: str, base: str, head: str, before: str) -> tuple[str, str] | None:
    after = (head or "").strip()
    if not after:
        return None
    if comment_scope(action) == "push":
        start = (before or "").strip()
    else:
        start = (base or "").strip() or (before or "").strip()
    if not start or start == after:
        return None
    return start, after


def collect_linked_issues(
    *,
    body: str,
    owner: str,
    repo: str,
    token: str,
    pr_number: int,
) -> set[int]:
    linked = parse_closing_issue_numbers(body)
    if token:
        linked |= linked_from_graphql(owner, repo, token, pr_number)
        linked |= linked_from_timeline(owner, repo, token, pr_number)
    return linked


def cmd_sync(args: argparse.Namespace) -> int:
    if should_skip_draft(args.draft):
        print("草稿 PR，不同步 Issue")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or ""
    repo_sl = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or "/" not in repo_sl:
        print("需要 GITHUB_TOKEN 与 GITHUB_REPOSITORY", file=sys.stderr)
        return 1
    owner, repo = repo_sl.split("/", 1)
    cwd = repo_root()
    action = args.action
    pr_number = int(args.pr)
    body = _read_text(args.body_file) if args.body_file else (args.body or "")
    if args.previous_body_file:
        previous_body = _read_text(args.previous_body_file)
    elif args.previous_body is not None:
        previous_body = args.previous_body
    else:
        previous_body = body

    current = collect_linked_issues(
        body=body,
        owner=owner,
        repo=repo,
        token=token,
        pr_number=pr_number,
    )
    previous = parse_closing_issue_numbers(previous_body)
    if action != "edited":
        previous = set()
    targets = issues_to_comment(action, current, previous)
    if not targets:
        print("无待写入的关联 Issue，跳过")
        return 0

    rng = resolve_diff_range(action, args.base, args.head, args.before)
    if rng is None:
        print("无法确定 diff 区间，跳过")
        return 0
    start, after = rng
    paths = changed_paths(start, after, cwd)
    if not paths:
        print("无文件变更，跳过")
        return 0

    hint = args.title or os.environ.get("PR_TITLE") or commit_hint(start, after, cwd)
    summary = summarize_with_llm(
        paths=paths,
        diff=unified_diff(start, after, cwd),
        hint=hint,
    ) or fallback_summary(paths, hint)
    scope = comment_scope(action)
    comment = format_progress_comment(
        pr_number=pr_number,
        sha=after,
        paths=paths,
        summary=summary,
        scope=scope,
    )

    posted = 0
    for number in sorted(targets):
        comments = list_comments(owner, repo, token, number)
        if already_synced(comments, after):
            print(f"Issue #{number} 已有 {after[:12]}，跳过")
            continue
        if args.dry_run:
            print(f"[dry-run] 将评论 Issue #{number}")
            posted += 1
            continue
        post_comment(owner, repo, token, number, comment)
        print(f"已写入 Issue #{number}")
        posted += 1
    if posted == 0:
        print("没有新评论")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将 PR 改动摘要同步到关联的需求 Issue")
    parser.add_argument("--pr", required=True, help="PR 编号")
    parser.add_argument(
        "--action",
        required=True,
        choices=("opened", "synchronize", "ready_for_review", "edited"),
    )
    parser.add_argument("--head", required=True, help="PR head SHA")
    parser.add_argument("--base", default="", help="PR base SHA（opened / ready / edited 用）")
    parser.add_argument("--before", default="", help="上一推 SHA（synchronize 用）")
    parser.add_argument("--body", default="", help="当前 PR 描述")
    parser.add_argument("--body-file", default="", help="当前 PR 描述文件")
    parser.add_argument("--previous-body", default=None, help="edited 之前的 PR 描述")
    parser.add_argument("--previous-body-file", default="", help="edited 之前的 PR 描述文件")
    parser.add_argument("--title", default="", help="PR 标题")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return cmd_sync(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
