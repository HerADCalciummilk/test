"""L1 审核规则定义。

职责：集中维护规则 ID、严重级别、说明文案，以及匹配用的常量/正则。
检查逻辑在 l1_review.py；PR 评论渲染在 format_l1_comment.py。
对外说明见 docs/L1_机器审核规范.md。

严重级别：
- blocker：检查失败，workflow 红灯，开发者需修复后再推。
- warning：写入 l1-review.json 与 PR 评论，不单独阻断合并。

改规则时改本文件（必要时同步改 l1_review.py 与规范文档），经 PR 合入后全员生效。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["blocker", "warning"]


@dataclass(frozen=True)
class Rule:
    """单条规则的元数据；severity 决定是否令 job 失败。"""

    id: str
    severity: Severity
    title: str
    note: str


# ---------------------------------------------------------------------------
# 规则表：l1_review.py 通过 rule_id 引用；format_l1_comment.py 用 title 展示给人看
# ---------------------------------------------------------------------------
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
        severity="blocker",
        title="中间目录缺少必要子目录",
        note="00temp/ 亦须具备 src、cli、test、docs、nbs、resource；缺失则阻断。",
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
        title="flake8 风格、格式与命名问题",
        note="flake8 + pep8-naming（PEP 8，行宽 120）；含类名 CapWords（N801）等命名检查；应当修复，不单独阻断。",
    ),
    "NO_CONCRETE_PLUGIN": Rule(
        id="NO_CONCRETE_PLUGIN",
        severity="blocker",
        title="未找到具体插件类",
        note="00temp/ 与 NIMM/ 均须满足：src/（不含 utils）中至少有一个（直接或间接）继承 BasePlugin 或 PostProcessingPlugin 的具体插件类。",
    ),
    "PLUGIN_MISSING_INIT": Rule(
        id="PLUGIN_MISSING_INIT",
        severity="blocker",
        title="具体插件缺少 __init__",
        note="具体插件类须定义 __init__（无参时可为空实现）。",
    ),
    "PLUGIN_MISSING_PROCESS": Rule(
        id="PLUGIN_MISSING_PROCESS",
        severity="blocker",
        title="具体插件缺少 process",
        note="具体插件类须定义非空 process 作为主入口。",
    ),
    "PLUGIN_EMPTY_PROCESS": Rule(
        id="PLUGIN_EMPTY_PROCESS",
        severity="blocker",
        title="具体插件 process 为空",
        note="process 不能仅有 docstring / pass / ...；禁止空实现凑检。",
    ),
    "PYTHON_SYNTAX_ERROR": Rule(
        id="PYTHON_SYNTAX_ERROR",
        severity="blocker",
        title="Python 语法错误",
        note="文件无法被解析，导入或运行必失败；须修复后再合入。",
    ),
    "PLUGIN_BASE_CHAIN": Rule(
        id="PLUGIN_BASE_CHAIN",
        severity="warning",
        title="PostProcessingPlugin 未继承 BasePlugin",
        note="中间基类允许扩展，但应直接或名义上挂在 BasePlugin 下（本检查仅看直接基类名）。",
    ),
    "EMPTY_REQUIRED_DIR": Rule(
        id="EMPTY_REQUIRED_DIR",
        severity="warning",
        title="必要目录无实质内容",
        note="目录已存在但无文件、或仅有 .gitkeep 占位；不含已缺失目录（缺目录为 blocker）。",
    ),
}

# CODEX 约定的算法包必要子目录（中间目录与正式目录均强制，级别见上表）
REQUIRED_PACKAGE_DIRS = ("src", "cli", "test", "docs", "nbs", "resource")

# 仅占位、不算实质内容的文件名（如 resource/.gitkeep）
PLACEHOLDER_FILE_NAMES = frozenset({".gitkeep"})

# 插件继承识别：具体插件 =（直接或间接）继承下列基类，且类名不是这些基类本身
PLUGIN_BASE_NAMES = frozenset({"BasePlugin", "PostProcessingPlugin"})

# 不在这些 src 子目录中要求插件形态（仍参与继承图，便于解析间接继承）
PLUGIN_SKIP_SRC_DIR_NAMES = frozenset({"utils"})

# 内容扫描用正则 / 后缀（由 l1_review.py 的 check_* 使用）
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

# 遍历仓库时跳过的目录 / 不做文本规则扫描的后缀
SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".ipynb_checkpoints",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}

SKIP_FILE_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".nc", ".grib", ".grb"}

# 过大文本不读入做内容匹配，避免拖慢 CI
MAX_TEXT_FILE_BYTES = 1_000_000

# PR 评论中的隐藏标记：用于统计「第 N 次」检查（每次追加新评论，不覆盖）
COMMENT_MARKER_L1 = "<!-- nimm-l1-review -->"
COMMENT_MARKER_L2 = "<!-- nimm-l2-review -->"
