"""L1 审核规则。

blocker：检查失败，workflow 红灯，开发者需修复后再推。
warning：写入 review.json 与 PR 评论，不单独阻断合并。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["blocker", "warning"]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    title: str
    note: str


RULES = {
    "CREDENTIAL_PATTERN": Rule(
        id="CREDENTIAL_PATTERN",
        severity="blocker",
        title="疑似凭据或私钥",
        note="仓库一般不含密钥；仅拦截误提交的私钥或典型云密钥。",
    ),
    "MISSING_REQUIRED_DIR_OFFICIAL": Rule(
        id="MISSING_REQUIRED_DIR_OFFICIAL",
        severity="blocker",
        title="正式目录缺少必要子目录",
        note="NIMM/ 下算法包必须有 src、cli、test、docs、nbs、resource。",
    ),
    "MISSING_REQUIRED_DIR": Rule(
        id="MISSING_REQUIRED_DIR",
        severity="warning",
        title="中间目录缺少必要子目录",
        note="00temp/ 下缺失只警告，正式入库再收紧。",
    ),
    "HARDCODED_BIZ_PATH": Rule(
        id="HARDCODED_BIZ_PATH",
        severity="warning",
        title="硬编码业务路径",
        note="如 /home/nimm。中间目录常见，正式入库前应去掉。",
    ),
    "PLUGIN_FILE_IO": Rule(
        id="PLUGIN_FILE_IO",
        severity="warning",
        title="src 中疑似文件 I/O",
        note="规范要求插件 process() 不读写文件；当前先警告。",
    ),
    "UNDECLARED_NATIVE_BINARY": Rule(
        id="UNDECLARED_NATIVE_BINARY",
        severity="warning",
        title="未说明的二进制扩展",
        note=".so/.pyd/.dll 需在 docs 中说明用途和平台。",
    ),
    "FLAKE8": Rule(
        id="FLAKE8",
        severity="warning",
        title="flake8 风格问题",
        note="属于静态扫描，应当修复，不单独阻断。",
    ),
    "BLACK": Rule(
        id="BLACK",
        severity="warning",
        title="Black 格式不一致",
        note="属于静态扫描，应当修复，不单独阻断。",
    ),
}

REQUIRED_PACKAGE_DIRS = ("src", "cli", "test", "docs", "nbs", "resource")

HARDCODED_PATH_PATTERNS = (
    r"/home/nimm\b",
    r"/home/[^/\s\"']+/nimm\b",
)

CREDENTIAL_PATTERNS = (
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"AKIA[0-9A-Z]{16}",
)

PLUGIN_IO_PATTERNS = (
    r"\bopen\s*\(",
    r"\bread_csv\s*\(",
    r"\bto_csv\s*\(",
    r"\bPath\([^)]+\)\s*\.\s*write",
)

NATIVE_SUFFIXES = (".so", ".pyd", ".dll")

SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".ipynb_checkpoints",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}

SKIP_FILE_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".nc", ".grib", ".grb"}

MAX_TEXT_FILE_BYTES = 1_000_000

# 用于 PR 评论定位/更新同一条机器人评论
COMMENT_MARKER = "<!-- nimm-l1-review -->"
