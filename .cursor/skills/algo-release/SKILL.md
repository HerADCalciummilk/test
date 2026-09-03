---
name: algo-release
description: >-
  Creates a whole-repo GitHub Release (tag vX.Y.Z). Use when the user asks to
  发版, 打 Release, 发布下一版, 更新管理, or gh release create for this algorithm
  repository.
---

# 整仓发版（人触发 Tag + Release）

本仓库算法按 **一个库** 使用。版本只有一条线：`vX.Y.Z`。不要给单个算法包打 Tag。

需求用 Issue 规划（须选 Milestone）；实现用 PR（`Fixes #n`）。**合入不会自动发版**，也不要按 open Issue 数量决定是否发版。

## 何时用

用户要发布下一版、写 Release notes、或 `gh release create` 时使用本 skill。

## 步骤

复制并勾选：

```
发版进度：
- [ ] 1. 确认默认分支与上一 Tag
- [ ] 2. 看上一 Tag..HEAD 的提交 / 已合入 PR；可选核对 Milestone 中 Issue 是否已关
- [ ] 3. 建议 patch / minor / major（人确认）
- [ ] 4. 起草 notes（只要功能，不要写 PR/直推来源）
- [ ] 5. 人确认后 gh release create
```

### 1. 上一版本

```bash
git fetch --tags
git tag -l "v*" --sort=-v:refname
```

只认 `v` + 三段数字（`v1.2.1`）。没有 Tag 则下一版从 `v0.1.0` 或 `v1.0.0` 与用户确认。

### 2. 未发布内容

```bash
git log <上一Tag>..HEAD --oneline
gh pr list --state merged --base "$(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null || echo main)" --search "merged:>=$(git log -1 --format=%cI <上一Tag>)"
```

可选：`gh issue list --milestone vX.Y.Z --state all` 看该版本规划的需求是否已关。Milestone 进度不是发版门禁；仍有其它 Milestone 的 open Issue 时也可以发版。

没有相对上一 Tag 的提交则停止，不要空发版。

### 3. 建议版本号

相对上一 Tag：

- 修复 / 性能 / 文档且不影响使用方式 → patch（1.2.0 → 1.2.1）
- 兼容的新能力 → minor
- 不兼容（插件签名、输入输出语义破坏）→ major

只改 `.github` / `NIMM/utils` / 根文档时，询问用户是否跳过发版。

### 4. Release notes

**只要功能。** 可用：

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes --draft
```

核对后去掉草稿标记，或用 `--notes-file` 手写。不要把「来源：PR / 直推」写进 notes。

模板：

```markdown
## 变更

- （摘要 1）
- （摘要 2）

相对版本：v上一版
```

### 5. 创建 Release

人确认 Tag 与 notes 之后：

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes-file notes.md
```

不要用网页 New release，除非 `gh` 不可用。不要按包名打 Tag。不要在未确认时自动 `gh release create`。

合入时带 `Fixes #n` 的需求 Issue 会由 GitHub 关闭，发版工作流不必再关单。

### 6. 不要做的事

- 不要改算法代码来「制造」版本号
- 不要合入即自动 patch / 自动打 Tag
- 不要用全仓库 open Issue 数量作为发版条件
- 不要按包名打多个 Tag
- 不要把直推/PR 来源或 L1/L2 结论写进 notes
- 不要再创建「待发版」账本 Issue，也不要把 commit 流水账堆进需求 Issue
