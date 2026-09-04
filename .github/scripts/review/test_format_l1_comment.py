"""整条审核评论：共用 SHA 标题，静态检查与 LLM审核分节。"""

from __future__ import annotations

import unittest

from format_l1_comment import render_markdown
from format_l2_comment import render_markdown as render_l2
from rules import L2_SLOT_END, L2_SLOT_START, review_round_marker


class ReviewCommentRoundTests(unittest.TestCase):
    def test_shared_title_and_two_sections(self) -> None:
        sha = "abc1234deadbeef"
        text = render_markdown(
            {
                "summary": {"blocker_count": 0, "warning_count": 1},
                "packages": ["00temp/example_pkg"],
                "blockers": [],
                "warnings": [
                    {
                        "rule_id": "HARDCODED_BIZ_PATH",
                        "path": "00temp/example_pkg/src/plugin.py",
                        "line": 42,
                        "message": "硬编码路径 /home/nimm",
                    }
                ],
            },
            sha=sha,
            l2_status="pending",
            checked_at="2026-09-03 16:00:00 +0800",
        )
        self.assertIn(review_round_marker(sha), text)
        self.assertEqual(text.count("## 审核 `abc1234deadb`"), 1)
        self.assertIn("### 静态检查", text)
        self.assertIn("### LLM审核", text)
        self.assertIn("进行中，完成后此段会更新。", text)
        self.assertNotIn("第 ", text)
        self.assertNotIn("**L1**", text)
        self.assertNotIn("**L2**", text)
        self.assertIn(L2_SLOT_START, text)
        self.assertIn(L2_SLOT_END, text)
        self.assertLess(text.index("### 静态检查"), text.index("### LLM审核"))

    def test_skipped_when_machine_blocked(self) -> None:
        text = render_markdown(
            {
                "summary": {"blocker_count": 1, "warning_count": 0},
                "blockers": [
                    {
                        "rule_id": "PLUGIN_MISSING_PROCESS",
                        "path": "a.py",
                        "line": 1,
                        "message": "缺 process",
                    }
                ],
                "packages": ["NIMM/x/y"],
            },
            sha="fff",
            l2_status="pending",
            checked_at="t",
        )
        self.assertIn("未执行（静态检查未通过）。", text)
        self.assertIn("**结果**：未通过（存在阻断项）", text)
        self.assertNotIn("**L2**", text)

    def test_semantic_fragment_has_no_round_header(self) -> None:
        text = render_l2(
            {
                "gate": "l2",
                "packages": ["00temp/example_pkg"],
                "model": "gpt-4o-mini",
                "summary": {"risk_level": "medium", "finding_count": 1},
                "overview": "cli 未调用插件。",
                "findings": [
                    {
                        "severity": "medium",
                        "category": "cli",
                        "path": "cli/run.py",
                        "title": "cli 未调用插件业务",
                        "detail": "入口只打印 usage。",
                        "evidence": "print('TODO')",
                    }
                ],
            },
            sha="a1b2c3d4e5f6789012345678901234567890abcd",
            run_url="https://example.test/run",
            checked_at="2026-09-03 16:02:11 +0800",
        )
        self.assertIn("**结果**：有发现（不阻断合并）", text)
        self.assertIn("#### 总评", text)
        self.assertIn("#### 发现项", text)
        self.assertNotIn("## 审核", text)
        self.assertNotIn("**提交**", text)
        self.assertNotIn("**算法包**", text)
        self.assertNotIn("Actions", text)
        self.assertNotIn("### LLM审核", text)
        self.assertNotIn("**L2**", text)


if __name__ == "__main__":
    unittest.main()
