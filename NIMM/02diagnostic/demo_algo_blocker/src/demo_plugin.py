"""正式目录阻断演示包：故意缺少 CODEX 必要子目录。

仅保留 src/，缺少 cli、test、docs、nbs、resource，
应触发 MISSING_REQUIRED_DIR_OFFICIAL（blocker）。
"""


def process(value):
    return value
