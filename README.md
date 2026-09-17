# test

本仓库用于 **算法代码上传审核**，以及合入后的 **整仓发版**（人触发 `vX.Y.Z`）。

- [算法审核规范](docs/算法审核规范.md)（静态检查 + LLM审核，同一条 PR 评论）
- [算法代码更新管理](docs/算法更新管理.md)（需求 Issue + Milestone + 人触发 `vX.Y.Z`）
- [本地一键检查](local_review/README.md)（独立于 GitHub L1/L2，解压包后本机审）
- 审核 CI：`.github/workflows/algorithm-review.yml`（草稿 PR 也跑 L1/L2）
- 需求进展 CI：`.github/workflows/issue-progress.yml`（正式 PR 将「改了啥」写到已关联 Issue）

## 审核流水线

```text
Pull Request / 手动触发
  → L1 machine review
       ├─ 有 blocker → Checks 失败，本 run 不执行 L2
       └─ 通过 → L2 LLM review（使用 L1 Artifact 中的 l1-review.json）
```

分支保护在 GitHub **Settings → 分支规则** 里勾选必过的 Checks，不是脚本开关。建议勾 **`L1 machine review`**；**`L2 LLM review`** 依赖 API Key，一般不要勾成必过。

需求跟踪：先开 Issue（须选 Milestone，模板见 `.github/ISSUE_TEMPLATE/`），PR 描述写 `Fixes #`。合入不自动发版。

## 目录约定（摘要）

```text
# 中间目录（整理期）
00temp/<pkg>/{src,cli,test,docs,nbs,resource}/

# 正式目录（归档后）
NIMM/<kind>/<pkg>/                    # 源码
cli|test|docs|nbs|resource/<kind>/<pkg>/   # 配套（与 NIMM 同级）
```

公共库 `NIMM/utils/` 不识别为算法包；变更仍走静态检查的文件级规则与 LLM 变更文件审核。细节见 [算法审核规范](docs/算法审核规范.md)。

## 脚本布局

```text
.github/scripts/review/     # L1 / L2（GitHub CI）
local_review/               # 本地一键检查（独立，不复用上一行）
.github/scripts/release/    # 需求 Issue 进展同步：issue_sync.py
.github/ISSUE_TEMPLATE/     # 算法需求模板（须选 Milestone）
.github/pull_request_template.md
.cursor/skills/algo-release/  # 发版 Skill（人触发 gh release create）
```

## 本地命令

```bash
# —— 独立本地一键（推荐用于解压包后检查；与 CI 脚本无关）——
pip install -r local_review/requirements.txt
set OPENAI_API_KEY=sk-...
python -m local_review --path 00temp/<pkg> --out local-review-report.md
# 静态 → venv+pytest → LLM 合并总结写 MD。调试：--skip-run / --dry-run / --allow-skip-llm
python -m local_review.test_local_review

# —— GitHub 同款 L1/L2 脚本（CI 对齐调试）——
pip install -r .github/scripts/review/requirements.txt

# L1
python .github/scripts/review/l1_review.py --path 00temp/<pkg> --json l1-review.json
python .github/scripts/review/format_l1_comment.py --json l1-review.json --out l1-review-comment.md

# L2（dry-run 不调用 API）
python .github/scripts/review/l2_review.py --path 00temp/<pkg> --dry-run --json l2-review.json
python .github/scripts/review/format_l2_comment.py --json l2-review.json --out l2-review-comment.md

# 需求 Issue 进展同步单测
python .github/scripts/release/test_issue_sync.py
```

算法样例请放在独立测试分支中维护；合入 `main` 的 PR 应避免带入故意失败的样例，以免静态检查红灯。详见 [算法审核规范](docs/算法审核规范.md)。
