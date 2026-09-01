# test

本仓库用于 **算法代码上传审核**：L1 机器检查、L2 LLM 语义辅助、人工终审（L3）。

- [L1 机器审核规范](docs/L1_机器审核规范.md)
- [L2 LLM 审核规范](docs/L2_LLM审核规范.md)
- CI：`.github/workflows/algorithm-review.yml`

## 审核流水线

```text
Pull Request / 手动触发
  → L1 machine review
       ├─ 有 blocker → Checks 失败，本 run 不执行 L2
       └─ 通过 → L2 LLM review（使用 L1 Artifact 中的 l1-review.json）
```

分支保护建议必过：**`L1 machine review`**。按需勾选 **`L2 LLM review`**。

## 目录约定（摘要）

```text
# 中间目录（整理期）
00temp/<pkg>/{src,cli,test,docs,nbs,resource}/

# 正式目录（归档后）
NIMM/<kind>/<pkg>/                    # 源码
cli|test|docs|nbs|resource/<kind>/<pkg>/   # 配套（与 NIMM 同级）
```

公共库 `NIMM/utils/` 不识别为算法包；变更仍走 L1 文件级检查与 L2 变更文件语义审。细节见 L1/L2 规范。

## 脚本布局

```text
.github/scripts/review/
  common.py              # 包发现、git diff
  rules.py               # L1 规则定义
  l1_review.py           # → l1-review.json
  format_l1_comment.py
  l2_review.py             # → l2-review.json
  format_l2_comment.py
  requirements.txt
```

## 本地命令

```bash
pip install -r .github/scripts/review/requirements.txt

# L1
python .github/scripts/review/l1_review.py --path 00temp/<pkg> --json l1-review.json
python .github/scripts/review/format_l1_comment.py --json l1-review.json --out l1-review-comment.md

# L2（dry-run 不调用 API）
python .github/scripts/review/l2_review.py --path 00temp/<pkg> --dry-run --json l2-review.json
python .github/scripts/review/format_l2_comment.py --json l2-review.json --out l2-review-comment.md
```

算法样例请放在独立测试分支中维护；合入 `main` 的 PR 应避免带入故意失败的样例，以免 L1 红灯。详见 [L1 规范](docs/L1_机器审核规范.md)。
