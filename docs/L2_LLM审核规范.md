# L2 LLM 审核规范

本文档描述本仓库 **L2（LLM 语义）算法上传审核** 的目标、触发方式、报告格式与配置要求。  
实现位于 `.github/scripts/review/l2_review.py`、`format_l2_comment.py`。  
CI 入口为统一工作流 `.github/workflows/algorithm-review.yml` 中的 **job `l2`**（`L2 LLM review`）。

L1（机器规则）见 [L1_机器审核规范.md](./L1_机器审核规范.md)。L2 **不替代** L1 与人工终审。

---

## 1. 目标与范围

| 项目 | 说明 |
|------|------|
| 门禁级别 | L2（LLM 辅助，默认 **advisory**，发现项不单独阻断合并） |
| 审核对象 | PR 变更所涉及的算法包（包发现逻辑与 L1 相同） |
| 擅长 | 尽量全面的语义/工程意图核查（含 **cli 是否调用插件业务**）；输出 findings 供人工按严重度审核 |
| 不擅长 / 不做 | 替代目录/插件形态/flake8 等可规则化检查（由 L1 负责） |

分工建议：

| 层级 | 职责 |
|------|------|
| L1 | 结构、语法、插件形态、密钥模式、风格 |
| L2 | 语义与意图、证据型 findings |
| L3 | 人工按 findings 终审 |

---

## 2. 触发与流程（与 L1 同一次 run）

```text
Algorithm review
  ├─ job l1  机器检查 → Artifact l1-review-report-<run_id>
  │            └─ 有 blocker → 失败，本 run 不再跑 l2
  └─ job l2  needs: l1（仅成功时）→ 下载 l1-review.json → LLM → Artifact / 评论
```

- 触发：`pull_request` 或 `workflow_dispatch`（与 L1 相同，**一个** workflow）
- **不再**单独并行跑第二份 L1；L2 只下载 L1 Artifact 中的 `l1-review.json` 作摘要
- 评论：仅 `opened` / `synchronize` 且 `run_attempt==1` 时追加；标记 `<!-- nimm-l2-review -->`
- LLM 发现 / 高风险 → **不**因此红灯；缺 `OPENAI_API_KEY` 或调用失败 → job `l2` 失败

维护约定：不要再新增独立的 `l2-review.yml` 与 `l1` 并行；改 L2 步骤只动本 workflow 的 `l2` job。

---

## 3. 配置（GitHub Secrets）

| Secret | 必填 | 说明 |
|--------|------|------|
| `OPENAI_API_KEY` | 是（跑 L2 时） | API Key |
| `OPENAI_BASE_URL` | 否 | 兼容 OpenAI 的网关，默认 `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 否 | 默认 `gpt-4o-mini` |

分支保护：通常将 **`L1 machine review`** 设为必过；是否将 **`L2 LLM review`** 设为必过取决于你是否强制要求已配置 API。

---

## 4. 本地命令

```bash
pip install -r .github/scripts/review/requirements.txt

# 不调用模型，验证报告与评论渲染
python .github/scripts/review/l2_review.py --path 00temp/demo_algo_clean --dry-run --json l2-review.json
python .github/scripts/review/format_l2_comment.py --json l2-review.json --out l2-review-comment.md --attempt 1

# 正式调用（需环境变量）
set OPENAI_API_KEY=sk-...
python .github/scripts/review/l2_review.py --path 00temp/demo_algo_clean --json l2-review.json --l1-json l1-review.json
```

---

## 5. 报告 `l2-review.json`

| 字段 | 含义 |
|------|------|
| `gate` | 固定 `l2` |
| `packages` | 本次算法包列表 |
| `model` | 使用的模型名 |
| `skipped` / `skip_reason` | **流水线是否调用了 LLM**（无包 / 缺 Key / 调用失败等）；与「算法有无问题」无关 |
| `summary.risk_level` | 本趟**总体**风险：`low` / `medium` / `high` |
| `summary.finding_count` | 发现条数 |
| `overview` | 中文总评 |
| `findings[]` | **问题列表**（人工主要据此审核）；每条自有 `severity` |
| `error` | 调用失败时的错误信息 |

已去掉 `needs_human_attention`、`human_checklist`：人工直接按 findings（可优先看 high）审核即可。

### 5.1 cli 与全面核查

- 对 docs/src/cli 做尽量全面的语义核查。
- **cli** 须判断是否真正调用插件 `process`/业务入口；仅占位则写入 findings。
- 发现项默认仍不单独阻断合并（advisory）。

Artifact：`l2-review-report-<run_id>`（`l2-review.json` / `l2-review-comment.md`）。

---

## 6. 版本说明

| 日期 | 说明 |
|------|------|
| 2026-08-31 | 初版：OpenAI 兼容 API、独立 PR 评论与 Artifact、默认 advisory |
| 2026-08-31 | 并入 `algorithm-review.yml`：`needs: l1`，去掉 L2 内重复跑 L1 |
| 2026-08-31 | 与 L1 对称命名：`l2_review.py` / `format_l2_comment.py`；报告 `l2-review.json` |
| 2026-09-01 | 扩大核查范围；强调 cli 插件调用；移除 `needs_human_attention` 与 `human_checklist` |
