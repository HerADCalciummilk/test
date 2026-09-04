"""LLM审核：报告组装、模型 JSON 解析、无输入时跳过。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import l2_review
from l2_review import _extract_json_object, build_report, normalize_model_result


class ExtractJsonTests(unittest.TestCase):
    def test_fenced_and_preamble(self) -> None:
        fenced = '说明\n```json\n{"risk_level": "low", "overview": "ok", "findings": []}\n```\n'
        data = _extract_json_object(fenced)
        self.assertEqual(data["risk_level"], "low")

        raw = '前面一段话 {"risk_level": "medium", "overview": "x", "findings": []} 后面还有字'
        data = _extract_json_object(raw)
        self.assertEqual(data["risk_level"], "medium")

    def test_braces_inside_string(self) -> None:
        text = '{"overview": "含 {花括号}", "risk_level": "low", "findings": []}'
        data = _extract_json_object(text)
        self.assertEqual(data["overview"], "含 {花括号}")

    def test_invalid_raises(self) -> None:
        with self.assertRaises(ValueError):
            _extract_json_object("没有 JSON")


class NormalizeAndReportTests(unittest.TestCase):
    def test_normalize_clamps_enums(self) -> None:
        out = normalize_model_result(
            {
                "risk_level": "CRITICAL",
                "overview": "x",
                "findings": [{"severity": "nope", "category": "weird", "title": "t"}],
            }
        )
        self.assertEqual(out["risk_level"], "low")
        self.assertEqual(out["findings"][0]["severity"], "low")
        self.assertEqual(out["findings"][0]["category"], "other")

    def test_skipped_report(self) -> None:
        report = build_report(
            [],
            model="gpt-4o-mini",
            skipped=True,
            skip_reason="无算法包且无变更可读文件，跳过 LLM",
            result={
                "risk_level": "low",
                "overview": "未调用 LLM。",
                "findings": [],
            },
        )
        self.assertEqual(report["gate"], "l2")
        self.assertTrue(report["skipped"])
        self.assertEqual(report["summary"]["finding_count"], 0)


class SkipWhenNoInputTests(unittest.TestCase):
    def test_main_skips_without_path_or_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "l2-review.json"
            argv = ["l2_review.py", "--repo-root", tmp, "--json", str(report)]
            with patch("sys.argv", argv):
                code = l2_review.main()
            self.assertEqual(code, 0)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(data["skipped"])
            self.assertIn("无算法包", data["skip_reason"] or "")

    def test_dry_run_with_mid_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            src = repo / "00temp" / "demo" / "src"
            src.mkdir(parents=True)
            (src / "a.py").write_text("X = 1\n", encoding="utf-8")
            report = repo / "l2.json"
            argv = [
                "l2_review.py",
                "--repo-root",
                tmp,
                "--path",
                "00temp/demo",
                "--dry-run",
                "--json",
                str(report),
            ]
            with patch("sys.argv", argv):
                code = l2_review.main()
            self.assertEqual(code, 0)
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(data["skipped"])
            self.assertEqual(data["model"], "dry-run")
            self.assertEqual(data["packages"], ["00temp/demo"])


if __name__ == "__main__":
    unittest.main()
