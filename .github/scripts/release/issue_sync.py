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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

COMMENT_MARKER = "<!-- nimm-issue-sync -->"
MAX_DIFF_CHARS = 40_000
MAX_PATHS = 20
USER_AGENT = "nimm-issue-sync"
# GitHub 单页最多 100；翻页并设上限，避免超长时间线静默截断。
API_PER_PAGE = 100
API_MAX_PAGES = 10

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
可以提与「本次项」中哪一条相关，但不要宣称目标或验收已完成。
不要评价代码质量，不要猜测 diff 中未出现的需求。
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


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """在仓库根执行 git，不抛异常（由调用方看 returncode）。"""
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


def already_synced(
    comments: list[dict[str, Any]],
    sha: str,
    pr_number: int | None = None,
) -> bool:
    """同一 Issue 上已有「本 PR + 本 SHA」的进展评论则跳过。"""
    sha_needle = f"<!-- sha:{sha} -->"
    pr_needle = f"<!-- pr:{pr_number} -->" if pr_number is not None else ""
    for item in comments:
        body = item.get("body") or ""
        if COMMENT_MARKER not in body or sha_needle not in body:
            continue
        if pr_needle and pr_needle not in body:
            continue
        return True
    return False


def fallback_summary(paths: list[str], hint: str) -> str:
    """无 LLM 时的降级摘要：提交说明 + 路径列表。"""
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


BEIJING = timezone(timedelta(hours=8))


def format_progress_time(when: datetime | None = None) -> str:
    """进展评论时间：北京时间，形如 2026-09-03 11:56 +0800。"""
    stamp = when or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(BEIJING)
    return stamp.strftime("%Y-%m-%d %H:%M +0800")


def format_progress_comment(
    *,
    pr_number: int,
    sha: str,
    paths: list[str],
    summary: str,
    when: datetime | None = None,
) -> str:
    """Issue 进展评论正文；HTML 注释用于按 SHA 去重。"""
    shown = paths[:MAX_PATHS]
    bullets = [f"- `{p}`" for p in shown]
    extra = len(paths) - len(shown)
    if extra > 0:
        bullets.append(f"- … 另有 {extra} 个文件")
    if not bullets:
        bullets.append("- （无）")
    return "\n".join(
        [
            COMMENT_MARKER,
            f"<!-- sha:{sha} -->",
            f"<!-- pr:{pr_number} -->",
            f"## PR #{pr_number}",
            "",
            f"- 时间：{format_progress_time(when)}",
            f"- 提交：`{sha[:12]}`",
            "- 路径：",
            *bullets,
            "",
            "### 改了什么",
            summary.strip(),
            "",
        ]
    )


def changed_paths(before: str, after: str, cwd: Path) -> list[str]:
    """before..after 的变更路径（含删除）。"""
    result = run_git(
        ["diff", "--name-only", "--diff-filter=ACMRD", before, after, "--"],
        cwd,
    )
    if result.returncode != 0:
        print(result.stderr or "git diff 失败", file=sys.stderr)
        return []
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def intersect_push_with_base(push_paths: list[str], vs_base_paths: list[str]) -> list[str]:
    """再 push：只保留「这一推改过、且相对此刻目标分支尖仍不同」的路径。

    必须和现在的 main 尖比，不能和开 PR 时的 base.sha 比。
    merge 带进来的别人的文件已经和当前 main 一样，第二份 diff 里没有它们。
    """
    keep = set(vs_base_paths)
    return [path for path in push_paths if path in keep]


def unified_diff(before: str, after: str, cwd: Path, paths: list[str] | None = None) -> str:
    """before..after 的 unified diff，超长截断后给 LLM。可限定路径。"""
    args = ["diff", before, after]
    if paths:
        args.extend(["--", *paths])
    else:
        args.append("--")
    result = run_git(args, cwd)
    text = result.stdout or ""
    if len(text) > MAX_DIFF_CHARS:
        return text[: MAX_DIFF_CHARS - 20] + "\n\n...[truncated]...\n"
    return text


def commit_hint(before: str, after: str, cwd: Path) -> str:
    """区间内 commit subject，拼成 LLM 提示。"""
    result = run_git(["log", "--format=%s", f"{before}..{after}"], cwd)
    if result.returncode != 0:
        return ""
    messages = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    return "；".join(messages[:8])


def _headers(token: str, *, json_body: bool = False, extra: dict[str, str] | None = None) -> dict[str, str]:
    """GitHub REST/GraphQL 共用请求头。"""
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
    """GitHub REST：返回解析后的 JSON；空 body 为 None。"""
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


def fetch_all_pages(
    fetch_page: Callable[[int], Any],
    *,
    per_page: int = API_PER_PAGE,
    max_pages: int = API_MAX_PAGES,
    label: str,
) -> list[Any]:
    """按 page=1,2,… 拉取直到不满一页。后续页失败时保留已拉到的条目并告警。"""
    items: list[Any] = []
    for page in range(1, max_pages + 1):
        try:
            chunk = fetch_page(page)
        except RuntimeError as exc:
            if not items:
                raise
            print(
                f"{label} 第 {page} 页失败，使用已拉取的 {len(items)} 条：{exc}",
                file=sys.stderr,
            )
            break
        if chunk is None:
            chunk = []
        if not isinstance(chunk, list):
            if not items:
                return []
            print(f"{label} 第 {page} 页不是列表，停止翻页", file=sys.stderr)
            break
        items.extend(chunk)
        if len(chunk) < per_page:
            break
        if page == max_pages:
            print(
                f"{label} 已拉 {max_pages} 页仍满页，后续事件未读入（共 {len(items)} 条）",
                file=sys.stderr,
            )
    return items


def graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """GitHub GraphQL；仅 errors 且无 data 时抛错。"""
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
    """closingIssuesReferences：Fixes 等会关闭的 Issue。"""
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


def linked_issue_numbers_from_timeline(items: list[Any]) -> set[int]:
    """按时间回放 Development 连接事件：connected 加入，disconnected 去掉。"""
    events = [item for item in items if isinstance(item, dict)]
    events.sort(key=lambda item: str(item.get("created_at") or ""))
    linked: set[int] = set()
    for event in events:
        kind = event.get("event")
        if kind not in ("connected", "disconnected"):
            continue
        source = event.get("source") or {}
        issue = source.get("issue") or source
        number = issue.get("number") if isinstance(issue, dict) else None
        if number is None:
            continue
        try:
            n = int(number)
        except (TypeError, ValueError):
            continue
        if kind == "connected":
            linked.add(n)
        else:
            linked.discard(n)
    return linked


def linked_from_timeline(owner: str, repo: str, token: str, pr_number: int) -> set[int]:
    """Development 栏「已连接」但未写 Fixes 时，closingIssuesReferences 可能为空。"""

    def fetch_page(page: int) -> Any:
        return _api(
            "GET",
            (
                f"/repos/{owner}/{repo}/issues/{pr_number}/timeline"
                f"?per_page={API_PER_PAGE}&page={page}"
            ),
            token,
            extra_headers={"Accept": "application/vnd.github+json"},
        )

    try:
        items = fetch_all_pages(fetch_page, label="PR timeline")
    except RuntimeError as exc:
        print(f"读取 PR timeline 失败：{exc}", file=sys.stderr)
        return set()
    return linked_issue_numbers_from_timeline(items)


def list_comments(owner: str, repo: str, token: str, issue_number: int) -> list[dict[str, Any]]:
    """Issue 现有评论，供 already_synced 判断。"""

    def fetch_page(page: int) -> Any:
        return _api(
            "GET",
            (
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments"
                f"?per_page={API_PER_PAGE}&page={page}"
            ),
            token,
        )

    items = fetch_all_pages(fetch_page, label=f"Issue #{issue_number} comments")
    return [item for item in items if isinstance(item, dict)]


def post_comment(owner: str, repo: str, token: str, issue_number: int, body: str) -> None:
    """向 Issue 追加一条评论。"""
    _api(
        "POST",
        f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
        token,
        {"body": body},
    )


def summarize_with_llm(*, paths: list[str], diff: str, hint: str) -> str | None:
    """有 OPENAI_API_KEY 时生成中文「改了什么」；失败返回 None 走降级。"""
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
    """opened/ready/edited 相对 base；synchronize 相对上一推。区间无效则 None。"""
    after = (head or "").strip()
    if not after:
        return None
    if action == "synchronize":
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
    """描述里的 Fixes + GraphQL 关闭关系 + Development 栏 connected。"""
    linked = parse_closing_issue_numbers(body)
    if token:
        linked |= linked_from_graphql(owner, repo, token, pr_number)
        linked |= linked_from_timeline(owner, repo, token, pr_number)
    return linked


def cmd_sync(args: argparse.Namespace) -> int:
    """一次 PR 事件：找出关联 Issue，写（或跳过）进展评论。"""
    if args.draft:
        print("草稿 PR，不同步 Issue")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or ""
    repo_sl = os.environ.get("GITHUB_REPOSITORY") or ""
    if not token or "/" not in repo_sl:
        print("需要 GITHUB_TOKEN 与 GITHUB_REPOSITORY", file=sys.stderr)
        return 1
    owner, repo = repo_sl.split("/", 1)
    cwd = Path(os.environ.get("GITHUB_WORKSPACE") or Path.cwd())
    action = args.action
    pr_number = int(args.pr)
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else (args.body or "")

    current = collect_linked_issues(
        body=body,
        owner=owner,
        repo=repo,
        token=token,
        pr_number=pr_number,
    )
    if not current:
        print("无待写入的关联 Issue，跳过")
        return 0

    rng = resolve_diff_range(action, args.base, args.head, args.before)
    if rng is None:
        print("无法确定 diff 区间，跳过")
        return 0
    start, after = rng
    pending: list[int] = []
    for number in sorted(current):
        comments = list_comments(owner, repo, token, number)
        if already_synced(comments, after, pr_number):
            print(f"Issue #{number} 已有 {after[:12]}，跳过")
            continue
        pending.append(number)
    if not pending:
        print("没有新评论")
        return 0

    paths = changed_paths(start, after, cwd)
    if action == "synchronize" and (args.base or "").strip():
        paths = intersect_push_with_base(
            paths,
            changed_paths(args.base.strip(), after, cwd),
        )
    if not paths:
        print("无文件变更，跳过")
        return 0

    hint = args.title or os.environ.get("PR_TITLE") or commit_hint(start, after, cwd)
    summary = summarize_with_llm(
        paths=paths,
        diff=unified_diff(start, after, cwd, paths=paths),
        hint=hint,
    ) or fallback_summary(paths, hint)
    comment = format_progress_comment(
        pr_number=pr_number,
        sha=after,
        paths=paths,
        summary=summary,
    )

    posted = 0
    for number in pending:
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
