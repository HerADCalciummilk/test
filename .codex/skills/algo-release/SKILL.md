---
name: algo-release
description: >-
  Creates a whole-repo GitHub Release (tag vX.Y.Z). Use when the user asks to
  发版, 打 Release, 发布下一版, 更新管理, or gh release create for this algorithm
  repository.
---

# 整仓发版（人触发 Tag + Release）

本仓库算法按 **一个库** 使用。版本只有一条线：`vX.Y.Z`。不要给单个算法包打 Tag。

需求用 Issue 规划（须选 Milestone）；实现用 PR（`Fixes #n`）。**合入不会自动发版**。

```
发版进度：
- [ ] 1. git tag -l "v*" --sort=-v:refname（只认 vX.Y.Z）
- [ ] 2. git log <上一Tag>..HEAD；可选 gh issue list --milestone vX.Y.Z
- [ ] 3. 建议 patch / minor / major（人确认）
- [ ] 4. notes 只要功能摘要
- [ ] 5. 人确认后：gh release create vX.Y.Z --title "vX.Y.Z" --notes-file notes.md
```

不要合入即自动打 Tag。不要用 open Issue 数量当发版门禁。不要再创建待发版账本 Issue。
