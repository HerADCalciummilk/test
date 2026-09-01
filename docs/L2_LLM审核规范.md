# L2 LLM 审核规范

本文档说明本仓库 **L2（LLM 语义）算法上传审核** 的行为：触发条件、上下文采集、模型要求、报告格式与配置。

- 实现代码：`.github/scripts/review/l2_review.py`、`format_l2_comment.py`
- CI 入口：`.github/workflows/algorithm-review.yml` 中的 job **`l2`**（Checks 名称 **`L2 LLM review`**）
- 机器规则：见 [L1_机器审核规范.md](./L1_机器审核规范.md)

L2 为 **advisory**：findings 不单独导致 job 失败（缺 API Key 或调用失败除外）。L2 辅助人工，不替代 L1 与人工终审。

---

## 1. 职责与边界

| 项目 | 说明 |
|------|------|
| 输入 | PR 变更识别到的算法包上下文，以及未成包的变更可读文件 |
| 输出 | `l2-review.json`：总体风险、overview、findings 列表 |
| L1 分工 | 目录、插件形态、语法、flake8、密钥等由 L1 负责；L2 侧重语义与工程意图 |
| L3 | 人工按 findings 终审 |

---

## 2. 何时运行 LLM

### 2.1 CI 流程

```text
Algorithm review
  ├─ job l1  机器检查 → Artifact（含 l1-review.json）
  │            └─ 存在 blocker → job 失败，本 run 不执行 l2
  └─ job l2  needs: l1 成功 → 下载 l1-review.json → 调用 LLM → Artifact / 评论
```

- 触发事件与 L1 相同：`pull_request` 或 `workflow_dispatch`
- L2 使用 L1 Artifact 中的 `l1-review.json` 作摘要，不在 L2 job 内重复跑 L1
- L2 findings 或高风险 **不**单独令 job 失败
- 未配置 `OPENAI_API_KEY` 或 API 调用/解析失败 → job `l2` 失败

### 2.2 跳过 LLM 的情况

| 情况 | 行为 |
|------|------|
| L1 存在 blocker | 本 run 不执行 L2 |
| 既无算法包、又无变更可读文件 | 写出报告，`skipped: true` |
| 未配置 API Key | 写出报告，`skipped: true`，job 失败 |
| API 调用或 JSON 解析失败 | 写出报告，`skipped: true`，job 失败 |
| `--dry-run` | 不调用模型，验证报告格式 |

**以下情况会调用 LLM**（在 L1 通过且 API 可用时）：

- 识别到至少一个算法包
- 仅有未成包的变更文件（如 `NIMM/utils`、文档、脚本）
- 同一 PR 中两者兼有

---

## 3. 上下文采集

一次 LLM 调用可包含多段上下文（拼在同一 user prompt 中）。

### 3.1 算法包上下文

包发现规则与 L1 相同（见 L1 规范第 2 节）。对每个识别到的包，采集可读文本（`.py`、`.md`、`.txt`、`.rst`），优先级：**docs → 源码 → cli**。

| 布局 | docs | 源码 | cli |
|------|------|------|-----|
| 中间 | `00temp/<pkg>/docs/` | `00temp/<pkg>/src/` | `00temp/<pkg>/cli/` |
| 正式 | `docs/<kind>/<pkg>/` | `NIMM/<kind>/<pkg>/` | `cli/<kind>/<pkg>/` |

正式算法的 cli 位于仓库根 `cli/<kind>/<pkg>/`；源码在 `NIMM/<kind>/<pkg>/`。L2 按上述路径采集，**不**将「NIMM 内缺少 cli 子目录」作为结构问题。

单文件与总上下文有长度上限（实现中约 12k 字符/文件、60k 字符/次），超出部分截断或省略。

### 3.2 非包变更上下文

变更文件未落入任何已识别算法包的扫描根时，单独成段：

- 标题标明「非算法包变更」或「未识别到算法包时的变更文件」
- 内容仅为**本次变更**中的可读文件
- 说明中要求：按给定文件做语义与风险核查；若无 cli/插件内容则不要臆造整包结构问题

### 3.3 L1 摘要

若存在 `l1-review.json`，将其 blocker/warning 摘要附加到 user prompt，供模型参考；模型应避免简单重复 L1 已判定的条目。

---

## 4. 模型核查要求

System prompt 要求模型输出**单个 JSON 对象**（无 Markdown 围栏），字段包括：

- `risk_level`：`low` | `medium` | `high`
- `overview`：中文总评
- `findings[]`：每条含 `severity`、`category`、`path`、`title`、`detail`、`evidence`

### 4.1 算法包场景

在可见的 docs / 源码 / cli 范围内核查：

1. 算法与插件逻辑是否像真实业务实现（含 `process` 是否空壳）
2. **cli 是否调用插件业务**：应实例化具体插件并调用 `process`（或约定主入口）；仅 print/占位须写入 findings
3. 与 docs 描述、命名与领域概念是否一致
4. 硬编码假设、隐蔽 I/O、不安全执行、明显工程问题等
5. 其它入库前应知晓的问题

有可读 cli 文件时，须在 findings 或 overview 中明确是否调用插件业务。

### 4.2 非包变更场景

按给定变更文件做语义与风险核查；信息不足时在 overview 说明局限，`findings` 可为空。不套用六树齐全、整包 cli 等算法包专属假设。

### 4.3 输出约定

- 不输出 `needs_human_attention`、`human_checklist`
- 信息不足时 `risk_level` 用 `low`，在 overview 说明

---

## 5. 配置

| Secret / 变量 | 必填 | 说明 |
|---------------|------|------|
| `OPENAI_API_KEY` | 是（跑 L2 时） | API Key |
| `OPENAI_BASE_URL` | 否 | OpenAI 兼容网关，默认 `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 否 | 默认 `gpt-4o-mini` |

分支保护：通常将 **`L1 machine review`** 设为必过；是否将 **`L2 LLM review`** 设为必过，取决于是否强制要求已配置 API 并成功执行 L2。

---

## 6. 本地命令

```bash
pip install -r .github/scripts/review/requirements.txt

# 验证报告与评论渲染（不调用模型）
python .github/scripts/review/l2_review.py --path 00temp/<pkg> --dry-run --json l2-review.json
python .github/scripts/review/format_l2_comment.py --json l2-review.json --out l2-review-comment.md --attempt 1

# 调用模型（需环境变量）
set OPENAI_API_KEY=sk-...
python .github/scripts/review/l2_review.py --path 00temp/<pkg> --json l2-review.json --l1-json l1-review.json

# 仅公共库变更（示例）
python .github/scripts/review/l2_review.py --path NIMM/utils --dry-run --json l2-utils.json
```

`--path` 若不能解析为算法包，会将该路径下文件作为变更上下文（见第 3.2 节）。

---

## 7. 报告 `l2-review.json`

| 字段 | 含义 |
|------|------|
| `gate` | 固定 `l2` |
| `packages` | 识别到的算法包 ID 列表（可为空） |
| `model` | 模型名；dry-run 时为 `dry-run` |
| `skipped` | 是否未调用 LLM |
| `skip_reason` | 跳过原因（无输入、缺 Key、调用失败等） |
| `summary.risk_level` | 本趟总体风险 |
| `summary.finding_count` | findings 条数 |
| `overview` | 中文总评 |
| `findings[]` | 问题列表，人工主要据此审核 |
| `error` | 调用失败时的错误信息 |

### PR 评论与 Artifact

- 评论：与 L1 相同，在 `opened` / `synchronize` 且 `run_attempt == 1` 时追加；标记 `<!-- nimm-l2-review -->`
- Artifact：`l2-review-report-<run_id>`，含 `l2-review.json`、`l2-review-comment.md`

---

## 8. 相关文件

| 路径 | 作用 |
|------|------|
| `.github/workflows/algorithm-review.yml` | CI：job `l2` |
| `.github/scripts/review/l2_review.py` | L2 入口 |
| `.github/scripts/review/format_l2_comment.py` | PR 评论渲染 |
| `.github/scripts/review/common.py` | 与 L1 共用的包发现 |

---

## 9. 文档维护

调整 L2 上下文范围、prompt 或报告字段时，请同步更新本文档并在实现 PR 中引用。
