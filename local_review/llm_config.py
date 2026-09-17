"""LLM 配置：环境变量优先，其次可选配置文件。"""

from __future__ import annotations

import os
from pathlib import Path

from .package import read_text

# 自动查找的文件名（只在本包目录下找，见 PACKAGE_CONFIG_DIR）
DEFAULT_LLM_CONFIG_NAMES = (
    "local_review.llm.toml",
    ".local_review.llm.toml",
)
# 配置与工具放在一起：仓库根文件多不便辨认，且本目录不再有其它 .toml
PACKAGE_CONFIG_DIR = Path(__file__).resolve().parent


def _parse_simple_toml(text: str) -> dict[str, str]:
    """极简 key = value 解析（与 review_run.toml 同风格）。"""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key:
            out[key] = val
    return out


def load_llm_file_config(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = read_text(path) or ""
    raw = _parse_simple_toml(text)
    mapped: dict[str, str] = {}
    # 兼容 openai_* 与简写
    aliases = {
        "api_key": "api_key",
        "openai_api_key": "api_key",
        "base_url": "base_url",
        "openai_base_url": "base_url",
        "model": "model",
        "openai_model": "model",
    }
    for k, v in raw.items():
        dest = aliases.get(k.lower())
        if dest and v:
            mapped[dest] = v
    return mapped


def resolve_llm_config(
    root: Path,
    *,
    config_path: Path | None = None,
) -> dict[str, str]:
    """合并文件与环境变量。优先级：环境变量 > --llm-config / 自动发现文件 > 默认值。

    自动发现只看 `local_review/` 自身目录；放到别处需用 --llm-config 指定
    （相对路径按 --root 解析）。
    """
    file_cfg: dict[str, str] = {}
    used_path = ""

    candidates: list[Path] = []
    if config_path is not None:
        candidates.append(config_path if config_path.is_absolute() else (root / config_path))
    else:
        candidates.extend(
            PACKAGE_CONFIG_DIR / name for name in DEFAULT_LLM_CONFIG_NAMES
        )

    seen: set[str] = set()
    for cand in candidates:
        key = str(cand.resolve()) if cand.exists() else str(cand)
        if key in seen:
            continue
        seen.add(key)
        loaded = load_llm_file_config(cand)
        if loaded:
            file_cfg = loaded
            used_path = str(cand)
            break

    api_key = (os.environ.get("OPENAI_API_KEY") or file_cfg.get("api_key") or "").strip()
    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        or file_cfg.get("base_url")
        or "https://api.openai.com/v1"
    ).strip()
    model = (
        os.environ.get("OPENAI_MODEL")
        or file_cfg.get("model")
        or "gpt-4o-mini"
    ).strip()

    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "config_path": used_path,
    }
