"""需求跟踪与整仓发版辅助脚本。

  issue_sync.py        正式 PR 的改动摘要 → 已关联需求 Issue
  test_issue_sync.py   纯函数单测（不访问网络）

CI：.github/workflows/issue-progress.yml
Skill：.cursor/skills/algo-release/SKILL.md
"""
