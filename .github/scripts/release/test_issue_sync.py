"""issue_sync.py 纯函数测试。"""

from __future__ import annotations

import unittest
import io
from contextlib import redirect_stderr
from datetime import datetime, timezone
from unittest.mock import patch

from issue_sync import (
    API_PER_PAGE,
    already_synced,
    build_progress_user_message,
    clip_text,
    fallback_summary,
    fetch_all_pages,
    format_progress_comment,
    format_progress_heading,
    intersect_push_with_base,
    linked_from_timeline,
    linked_issue_numbers_from_timeline,
    parse_closing_issue_numbers,
    parse_progress_llm,
    resolve_diff_range,
    sanitize_progress_title,
)


class ParseClosingTests(unittest.TestCase):
    def test_fixes_and_closes(self) -> None:
        text = "Fixes #12\nCloses #15\n"
        self.assertEqual(parse_closing_issue_numbers(text), {12, 15})

    def test_ignores_refs(self) -> None:
        self.assertEqual(parse_closing_issue_numbers("Refs #12\nRelated to #15"), set())

    def test_url_form(self) -> None:
        text = "Fixes https://github.com/acme/algo/issues/9"
        self.assertEqual(parse_closing_issue_numbers(text), {9})

    def test_owner_repo_hash(self) -> None:
        self.assertEqual(parse_closing_issue_numbers("Resolves acme/algo#4"), {4})

    def test_empty(self) -> None:
        self.assertEqual(parse_closing_issue_numbers(""), set())
        self.assertEqual(parse_closing_issue_numbers(None or ""), set())


class AlreadySyncedTests(unittest.TestCase):
    def _body(self, pr_number: int, sha: str) -> str:
        return format_progress_comment(
            pr_number=pr_number,
            sha=sha,
            paths=["a.py"],
            summary="改了阈值。",
            when=datetime(2026, 9, 3, 3, 56, tzinfo=timezone.utc),
        )

    def test_same_pr_same_sha_skips(self) -> None:
        body = self._body(8, "abc1234deadbeef")
        self.assertTrue(already_synced([{"body": body}], "abc1234deadbeef", 8))

    def test_missing_sha_is_new_binding(self) -> None:
        body = self._body(8, "aaa1111")
        self.assertFalse(already_synced([{"body": body}], "bbb2222", 8))
        self.assertFalse(already_synced([], "abc1234deadbeef", 8))

    def test_same_sha_other_pr_does_not_skip(self) -> None:
        body = self._body(8, "abc1234deadbeef")
        self.assertFalse(already_synced([{"body": body}], "abc1234deadbeef", 9))


class DiffRangeTests(unittest.TestCase):
    def test_diff_range(self) -> None:
        self.assertEqual(
            resolve_diff_range("synchronize", "base", "head", "prev"),
            ("prev", "head"),
        )
        self.assertEqual(
            resolve_diff_range("opened", "base", "head", "prev"),
            ("base", "head"),
        )
        self.assertEqual(
            resolve_diff_range("edited", "base", "head", ""),
            ("base", "head"),
        )
        self.assertIsNone(resolve_diff_range("synchronize", "base", "head", ""))
        self.assertIsNone(resolve_diff_range("opened", "same", "same", ""))


class PushPathFilterTests(unittest.TestCase):
    def test_drops_paths_only_brought_by_merging_base(self) -> None:
        push = [
            ".github/scripts/release/issue_sync.py",
            "docs/02diagnostic/demo_official_ok/README.md",
            "docs/算法更新管理.md",
        ]
        vs_base = ["docs/02diagnostic/demo_official_ok/README.md"]
        self.assertEqual(
            intersect_push_with_base(push, vs_base),
            ["docs/02diagnostic/demo_official_ok/README.md"],
        )

    def test_keeps_own_edit_to_file_also_on_base(self) -> None:
        self.assertEqual(
            intersect_push_with_base(["a.py", "b.py"], ["a.py", "b.py", "c.py"]),
            ["a.py", "b.py"],
        )

    def test_merge_only_push_is_empty(self) -> None:
        self.assertEqual(
            intersect_push_with_base(["from-main.py"], ["my.py"]),
            [],
        )


class CommentFormatTests(unittest.TestCase):
    def test_dedup_same_issue_sha(self) -> None:
        body = format_progress_comment(
            pr_number=8,
            sha="abc1234deadbeef",
            paths=["NIMM/02diagnostic/demo/a.py"],
            summary="改了阈值。",
            when=datetime(2026, 9, 3, 3, 56, tzinfo=timezone.utc),
        )
        self.assertIn("<!-- nimm-issue-sync -->", body)
        self.assertIn("<!-- sha:abc1234deadbeef -->", body)
        self.assertIn("## PR #8", body)
        self.assertNotIn("这一推", body)
        self.assertNotIn("相对 base", body)
        self.assertNotIn("人工勾选", body)
        self.assertIn("- 时间：2026-09-03 11:56 +0800", body)
        self.assertIn("### 本次修改：", body)
        self.assertNotIn("### 改了什么", body)
        self.assertTrue(already_synced([{"body": body}], "abc1234deadbeef", 8))
        self.assertFalse(already_synced([{"body": body}], "fff", 8))

    def test_fallback_paths(self) -> None:
        text = fallback_summary(["a.py", "b.py"], "")
        self.assertIn("`a.py`", text)
        self.assertIn("`b.py`", text)

    def test_heading_with_llm_title(self) -> None:
        self.assertEqual(
            format_progress_heading("更新 Issue #26 的复测说明"),
            "### 本次修改：更新 Issue #26 的复测说明",
        )

    def test_heading_fallback_has_no_short_title(self) -> None:
        self.assertEqual(format_progress_heading(""), "### 本次修改：")
        self.assertEqual(format_progress_heading("   "), "### 本次修改：")

    def test_comment_embeds_llm_title(self) -> None:
        body = format_progress_comment(
            pr_number=28,
            sha="bdf8ff45ec4d",
            paths=["a.py"],
            summary="更新了复测步骤。",
            title="更新 Issue #26 的复测说明",
            when=datetime(2026, 9, 4, 2, 49, tzinfo=timezone.utc),
        )
        self.assertIn("### 本次修改：更新 Issue #26 的复测说明", body)
        self.assertIn("更新了复测步骤。", body)


class ProgressLlmParseTests(unittest.TestCase):
    def test_json_title_and_body(self) -> None:
        raw = '{"title":"更新复测说明","body":"改了 README 里的步骤。"}'
        self.assertEqual(parse_progress_llm(raw), ("更新复测说明", "改了 README 里的步骤。"))

    def test_fenced_json(self) -> None:
        raw = '```json\n{"title":"修过滤","body":"去掉 merge 进来的路径。"}\n```'
        self.assertEqual(parse_progress_llm(raw), ("修过滤", "去掉 merge 进来的路径。"))

    def test_empty_body_is_failure(self) -> None:
        self.assertIsNone(parse_progress_llm('{"title":"只有标题","body":""}'))
        self.assertIsNone(parse_progress_llm(""))

    def test_prose_without_json_is_body_only(self) -> None:
        self.assertEqual(parse_progress_llm("改了阈值。"), ("", "改了阈值。"))

    def test_broken_json_is_failure(self) -> None:
        self.assertIsNone(parse_progress_llm('{"title":'))

    def test_strips_duplicated_prefix(self) -> None:
        self.assertEqual(sanitize_progress_title("本次修改：更新复测说明。"), "更新复测说明")


class ProgressUserMessageTests(unittest.TestCase):
    def test_user_message_is_diff_only(self) -> None:
        text = build_progress_user_message(
            paths=["a.py"],
            diff="diff --git a/a.py",
            hint="调阈值",
        )
        self.assertIn("调阈值", text)
        self.assertIn("a.py", text)
        self.assertIn("diff --git a/a.py", text)
        self.assertNotIn("本次项", text)
        self.assertNotIn("Issue #", text)

    def test_clip_text_truncates(self) -> None:
        text = clip_text("x" * 50, 30)
        self.assertLess(len(text), 50)
        self.assertIn("[truncated]", text)


class TimelineLinkTests(unittest.TestCase):
    def _ev(self, kind: str, number: int, when: str) -> dict:
        return {
            "event": kind,
            "created_at": when,
            "source": {"issue": {"number": number}},
        }

    def test_reconnect_after_disconnect(self) -> None:
        events = [
            self._ev("connected", 12, "2026-01-01T00:00:00Z"),
            self._ev("disconnected", 12, "2026-01-02T00:00:00Z"),
            self._ev("connected", 12, "2026-01-03T00:00:00Z"),
        ]
        self.assertEqual(linked_issue_numbers_from_timeline(events), {12})

    def test_last_event_is_disconnect(self) -> None:
        events = [
            self._ev("connected", 12, "2026-01-01T00:00:00Z"),
            self._ev("disconnected", 12, "2026-01-02T00:00:00Z"),
        ]
        self.assertEqual(linked_issue_numbers_from_timeline(events), set())

    def test_sorts_by_created_at(self) -> None:
        events = [
            self._ev("connected", 12, "2026-01-03T00:00:00Z"),
            self._ev("disconnected", 12, "2026-01-02T00:00:00Z"),
            self._ev("connected", 12, "2026-01-01T00:00:00Z"),
        ]
        self.assertEqual(linked_issue_numbers_from_timeline(events), {12})

    def test_ignores_other_events_and_bad_numbers(self) -> None:
        events = [
            {"event": "commented", "created_at": "2026-01-01T00:00:00Z"},
            self._ev("connected", 12, "2026-01-02T00:00:00Z"),
            {
                "event": "connected",
                "created_at": "2026-01-03T00:00:00Z",
                "source": {"issue": {"number": "nope"}},
            },
        ]
        self.assertEqual(linked_issue_numbers_from_timeline(events), {12})


class PaginatedFetchTests(unittest.TestCase):
    def test_stops_on_short_page(self) -> None:
        pages = {1: [{"n": 1}] * 100, 2: [{"n": 2}]}

        def fetch_page(page: int):
            return pages[page]

        items = fetch_all_pages(fetch_page, per_page=100, max_pages=10, label="t")
        self.assertEqual(len(items), 101)

    def test_keeps_earlier_pages_if_later_fails(self) -> None:
        def fetch_page(page: int):
            if page == 1:
                return [{"n": 1}] * 100
            raise RuntimeError("boom")

        buf = io.StringIO()
        with redirect_stderr(buf):
            items = fetch_all_pages(fetch_page, per_page=100, max_pages=10, label="t")
        self.assertEqual(len(items), 100)
        self.assertIn("第 2 页失败", buf.getvalue())

    def test_warns_when_max_pages_still_full(self) -> None:
        def fetch_page(page: int):
            return [{"n": page}] * 2

        buf = io.StringIO()
        with redirect_stderr(buf):
            items = fetch_all_pages(fetch_page, per_page=2, max_pages=3, label="t")
        self.assertEqual(len(items), 6)
        self.assertIn("仍满页", buf.getvalue())


class TimelineFetchTests(unittest.TestCase):
    def _ev(self, kind: str, number: int, when: str) -> dict:
        return {
            "event": kind,
            "created_at": when,
            "source": {"issue": {"number": number}},
        }

    def test_later_page_connection_is_kept(self) -> None:
        page1 = [self._ev("connected", 1, "2026-01-01T00:00:00Z")]
        page1.extend(
            {"event": "committed", "created_at": "2026-01-02T00:00:00Z"}
            for _ in range(API_PER_PAGE - 1)
        )
        page2 = [self._ev("connected", 2, "2026-01-03T00:00:00Z")]

        def fake_api(method, path, token, payload=None, extra_headers=None):
            if path.endswith("&page=2"):
                return page2
            if path.endswith("&page=1"):
                return page1
            return []

        with patch("issue_sync._api", side_effect=fake_api):
            found = linked_from_timeline("acme", "algo", "token", 8)
        self.assertEqual(found, {1, 2})


if __name__ == "__main__":
    unittest.main()
