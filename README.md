# test

本仓库用于开发 **算法代码上传审核**（L1 机器检查 + L2 LLM + 后续人工）。

- L1 规范：[docs/L1_机器审核规范.md](docs/L1_机器审核规范.md)
- L2 规范：[docs/L2_LLM审核规范.md](docs/L2_LLM审核规范.md)
- CI 入口：`.github/workflows/algorithm-review.yml`（job `l1` → 成功后 job `l2`）

## 目录速览

```text
.github/
  workflows/algorithm-review.yml
  scripts/review/
    common.py              # 共用包发现
    rules.py               # L1 规则与 marker
    l1_review.py           # → l1-review.json
    format_l1_comment.py
    l2_review.py           # → l2-review.json
    format_l2_comment.py
    requirements.txt
```

## 流水线

```text
Pull Request / 手动触发
  → L1 machine review（机器门禁）
       ├─ 有 blocker → 红灯，不跑 L2
       └─ 通过 → L2 LLM review（下载 l1-review.json，不重跑机器检查）
```

分支保护建议必过：**`L1 machine review`**。按需勾选 **`L2 LLM review`**。

## 本地命令

```bash
pip install -r .github/scripts/review/requirements.txt

# L1
python .github/scripts/review/l1_review.py --path 00temp/demo_algo_clean --json l1-review.json
python .github/scripts/review/format_l1_comment.py --json l1-review.json --out l1-review-comment.md

# L2（dry-run 不调 API）
python .github/scripts/review/l2_review.py --path 00temp/demo_algo_clean --dry-run --json l2-review.json
python .github/scripts/review/format_l2_comment.py --json l2-review.json --out l2-review-comment.md
```

样例包预期见 [docs/L1_机器审核规范.md](docs/L1_机器审核规范.md)。
