"""LLM：语义审 + 将静态结果润色合并为总评（独立实现）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import (
    CODE_SUFFIXES,
    DOC_SUFFIXES,
    MAX_FILE_CHARS,
    MAX_TOTAL_CHARS,
)
from .models import ReviewReport
from .package import PackageRef, iter_files, path_is_under, read_text, repo_rel

SYSTEM_PROMPT_BASE = """你是内部算法包的本地审核助手。根据「检查 JSON（含静态与 pytest 动态结果）」与「代码/文档摘录」给出评审。
**代码语义检查是必选**：即使静态/动态已有 blocker/warning，仍须审可读代码（空壳、逻辑、meb I/O、硬编码/隐蔽 I/O、不安全执行等）；有依据再写。
机器检查结果会由报告模板单独排版，你**不要**在 markdown_body 里重复罗列静态/动态条目，也不要再写「## 概述」「## 静态检查」「## 静态与动态检查结果」这类与模板重复的标题。
pytest：失败须写入 findings；通过可在 overview 一笔带过，勿夸大成业务完全正确。
meb 数据格式：**核心结论是 process/主入口的入参出参是否为 meb 数据格式**（网格或站点均可，不必区分二者）。
静态只给出注解、时空坐标等可复核证据，**实际逻辑是否真按此格式走须由你判断**。规范：
- 网格：底层 `xarray.DataArray`，维度顺序固定为 member、level、time、dtime、lat、lon 共六维，
  并带 units、model、dtime_units、level_type、time_type、time_bounds 六项 attrs（算法代码不一定直接读写这些属性）。
- 站点：`pandas.DataFrame`，前六列固定为 level、time、dtime、id、lat、lon（层次、时间、预报时效、站点 ID、经度、纬度）。
据此核对：入参是否按上述规范消费、返回是否仍是该格式；维度顺序不符、中途退化成裸 ndarray 后未还原、
入口同时接受非 meb 类型而未做校验、或仅 import 未真正使用，都算问题。
**结论必须写进下面 schema 的 `meb_verdict`（必填，不得省略）**；meb 相关问题一律只写在
`meb_verdict.issues` 里，**findings 中不得出现 meb 格式类条目**（category 也没有 meb 这一取值）；
即使静态已判「符合」，也要自行复核代码逻辑；材料不足就写 `unclear` 并说明缺什么。
依赖：静态已给出清单比对结果。若出现重量级依赖（DEP_HEAVY），请结合代码规模判断是否真有必要，这类必要性判断只有你能做。
注释：缺 docstring 以静态为准（只统计条数），**不要**把静态已列出的再写成 findings。
在此之上检查行内注释，但**只报两类有实际风险的**（category 用 docs，须指出具体代码位置）：
1. 注释与代码矛盾或明显过时（说明哪一行代码与注释对不上）；
2. 关键逻辑段落完全无注释（公式、魔数、分支阈值等看不懂就无法维护之处）。
泛泛的「建议补充注释说明参数含义」「注释偏少」一律不写。
只输出一个 JSON 对象（不要 Markdown 围栏），schema：
{
  "risk_level": "low"|"medium"|"high",
  "overview": "中文总评：简洁明了、把关键结论讲清楚即可，不限句数，不要重复条目列表",
  "meb_verdict": {
    "verdict": "yes"|"partial"|"no"|"unclear",
    "input": "入参是否为 meb 数据格式及其代码依据",
    "output": "出参是否为 meb 数据格式及其代码依据",
    "issues": ["逐条写具体问题；无问题则为空数组"],
    "basis": "关键代码位置，形如 src/xxx.py:120 或 类名.process"
  },
  "findings": [
    {
      "severity": "low"|"medium"|"high",
      "category": "docs"|"semantics"|"security"|"execution"|"other",
      "path": "相对路径或类名，未知则空字符串",
      "title": "短标题",
      "detail": "说明",
      "evidence": "依据"
    }
  ],
  "markdown_body": "仅含语义向内容的 Markdown：可用二级标题「## 改进建议」等；禁止重复机器检查清单"
}
若信息不足：risk_level=low，overview 说明局限，findings 可空，但 `meb_verdict` 仍须给出（verdict=unclear）。
"""


def build_system_prompt() -> str:
    return SYSTEM_PROMPT_BASE


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n...[truncated]...\n"


def collect_package_context(root: Path, package: PackageRef) -> str:
    chunks: list[str] = [
        f"## 算法包 `{package.package_id}`（{package.layout}）\n",
        "材料顺序：docs → 源码 → cli。未见则跳过，勿臆造。\n",
    ]
    used = 0
    docs_dir = package.docs_dir(root)
    src_dir = package.source_dir(root)
    cli_dir = package.cli_dir(root)

    candidates: list[Path] = []
    for d in (docs_dir, src_dir, cli_dir):
        if d.is_dir():
            candidates.extend(iter_files(d))

    def sort_key(p: Path) -> tuple[int, str]:
        rel = repo_rel(root, p)
        if docs_dir.is_dir() and path_is_under(p, docs_dir):
            pri = 0
        elif src_dir.is_dir() and path_is_under(p, src_dir):
            pri = 1
        else:
            pri = 2
        return (pri, rel)

    for path in sorted(candidates, key=sort_key):
        suffix = path.suffix.lower()
        if suffix not in DOC_SUFFIXES and suffix not in CODE_SUFFIXES:
            continue
        text = read_text(path)
        if text is None:
            continue
        rel = repo_rel(root, path)
        piece = _truncate(text, MAX_FILE_CHARS)
        block = f"### 文件 `{rel}`\n```\n{piece}\n```\n"
        if used + len(block) > MAX_TOTAL_CHARS:
            chunks.append("\n（其余文件因长度上限已省略）\n")
            break
        chunks.append(block)
        used += len(block)

    if used == 0:
        chunks.append("（未采集到可读文本）\n")
    return "\n".join(chunks)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


RETRY_HINT = (
    "上一条输出不是合法 JSON（解析失败）。请只输出一个合法 JSON 对象："
    "不要 Markdown 围栏，字符串内的换行与引号必须转义，字段与 schema 保持一致。"
)


def _complete(client: Any, model: str, messages: list[dict[str, str]], *, json_mode: bool) -> str:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("LLM 返回空内容")
    return content


def call_llm(
    *,
    report: ReviewReport,
    context: str,
    model: str,
    base_url: str,
    api_key: str,
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))
    static_json = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    user = (
        "### 静态检查 JSON\n```json\n"
        + _truncate(static_json, 20_000)
        + "\n```\n\n### 代码与文档摘录\n"
        + context
    )
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user},
    ]
    # 先试 JSON 模式；不支持该参数的端点会报错，退回普通模式
    try:
        content = _complete(client, model, messages, json_mode=True)
    except Exception:  # noqa: BLE001 — 参数不被支持时退回
        content = _complete(client, model, messages, json_mode=False)

    try:
        return _extract_json(content)
    except (json.JSONDecodeError, ValueError):
        # LLM 是必选环节，解析失败会丢掉整份语义审查，值得纠正重试一次
        retry = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": RETRY_HINT},
        ]
        return _extract_json(_complete(client, model, retry, json_mode=False))


def run_llm_or_skip(
    root: Path,
    package: PackageRef,
    report: ReviewReport,
    *,
    allow_skip_llm: bool,
    dry_run: bool,
    llm_config_path: Path | None = None,
) -> dict[str, Any]:
    """代码 LLM 默认为必选；仅 allow_skip_llm / dry_run 时跳过。"""
    from .llm_config import resolve_llm_config

    if dry_run or allow_skip_llm:
        return {
            "skipped": True,
            "skip_reason": "dry-run" if dry_run else "allow-skip-llm",
            "model": "dry-run" if dry_run else "",
        }

    cfg = resolve_llm_config(root, config_path=llm_config_path)
    api_key = cfg["api_key"]
    if not api_key:
        return {
            "skipped": True,
            "skip_reason": (
                "未配置 API Key（请设环境变量 OPENAI_API_KEY，"
                "或在 local_review/ 下放置 local_review.llm.toml / 使用 --llm-config）"
            ),
            "model": "",
            "llm_config_path": cfg.get("config_path", ""),
        }

    model = cfg["model"]
    base_url = cfg["base_url"]
    context = collect_package_context(root, package)
    try:
        data = call_llm(
            report=report,
            context=context,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        data["skipped"] = False
        data["model"] = model
        data["llm_config_path"] = cfg.get("config_path", "")
        return data
    except Exception as exc:  # noqa: BLE001 — 写入报告，由调用方决定退出码
        return {
            "skipped": True,
            "skip_reason": f"LLM 调用或解析失败: {exc}",
            "model": model,
            "llm_config_path": cfg.get("config_path", ""),
        }
