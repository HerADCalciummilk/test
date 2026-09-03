"""issue_sync.py 纯函数测试。"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from issue_sync import (
    already_synced,
    comment_scope,
    fallback_summary,
    format_progress_comment,
    issues_to_comment,
    newly_linked_issues,
    parse_closing_issue_numbers,
    resolve_diff_range,
    should_skip_draft,
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


class TargetIssueTests(unittest.TestCase):
    def test_opened_uses_all_current(self) -> None:
        self.assertEqual(issues_to_comment("opened", {12, 15}, {12}), {12, 15})

    def test_edited_only_new(self) -> None:
        self.assertEqual(issues_to_comment("edited", {12, 15}, {12}), {15})

    def test_edited_no_new(self) -> None:
        self.assertEqual(issues_to_comment("edited", {12}, {12}), set())

    def test_newly_linked(self) -> None:
        self.assertEqual(newly_linked_issues({12, 15}, {12}), {15})


class DraftAndScopeTests(unittest.TestCase):
    def test_skip_draft(self) -> None:
        self.assertTrue(should_skip_draft(True))
        self.assertFalse(should_skip_draft(False))

    def test_full_scope_actions(self) -> None:
        for action in ("opened", "ready_for_review", "edited"):
            self.assertEqual(comment_scope(action), "full")
        self.assertEqual(comment_scope("synchronize"), "push")

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


class CommentFormatTests(unittest.TestCase):
    def test_dedup_same_issue_sha(self) -> None:
        body = format_progress_comment(
            pr_number=8,
            sha="abc1234deadbeef",
            paths=["NIMM/02diagnostic/demo/a.py"],
            summary="改了阈值。",
            scope="push",
            when=datetime(2026, 9, 3, 3, 56, tzinfo=timezone.utc),
        )
        self.assertIn("<!-- nimm-issue-sync -->", body)
        self.assertIn("<!-- sha:abc1234deadbeef -->", body)
        self.assertIn("- 时间：2026-09-03 03:56 UTC", body)
        self.assertTrue(already_synced([{"body": body}], "abc1234deadbeef"))
        self.assertFalse(already_synced([{"body": body}], "fff"))

    def test_fallback_paths(self) -> None:
        text = fallback_summary(["a.py", "b.py"], "")
        self.assertIn("`a.py`", text)
        self.assertIn("`b.py`", text)


if __name__ == "__main__":
    unittest.main()
