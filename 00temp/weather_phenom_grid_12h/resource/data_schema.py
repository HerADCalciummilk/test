# -*- coding: utf-8 -*-
"""
数据结构常量（算法参数，与运行环境无关）
依据：QX/T 740-2024 附录A/B 及 SCMOC 数据规范

本模块仅包含算法层面的结构定义：
  - 变量分组规则（240h / 72h 变量）
  - 时间分辨率与时效上限
  - 起报时次约定

与运行环境相关的配置（DATA_ROOT、路径模板、辅助函数）
请见 resource/config.py。
"""

# ==============================================================================
# 一、变量分组
# ==============================================================================

# 240小时逐3小时预报的变量（预报时效: 003, 006, ..., 240）
VARS_240H: list[str] = ["R03", "PTYPE03", "TCC"]

# 72小时逐3小时预报的变量（预报时效: 003, 006, ..., 072）
VARS_72H: list[str] = ["FOG", "HAIL", "HAZE", "SAND", "THUNDER", "VIS"]

# 所有变量列表
ALL_VARS: list[str] = VARS_240H + VARS_72H


# ==============================================================================
# 二、时间分辨率与预报时效上限
# ==============================================================================

# 预报时间间隔（小时）
FORECAST_INTERVAL: int = 3

# 各类变量最大预报时效（小时）
MAX_FORECAST_HOUR_240: int = 240
MAX_FORECAST_HOUR_72:  int = 72

# 起报时次（UTC，每天00和12）
INIT_HOURS: list[int] = [0, 12]


# ==============================================================================
# 三、辅助函数
# ==============================================================================

def get_max_forecast_hour(var: str) -> int:
    """获取变量的最大预报时效"""
    if var in VARS_240H:
        return MAX_FORECAST_HOUR_240
    elif var in VARS_72H:
        return MAX_FORECAST_HOUR_72
    raise ValueError(f"未知变量: {var}，请检查 VARS_240H / VARS_72H 配置")


def get_forecast_hours(var: str) -> list[int]:
    """
    获取变量的所有预报时效列表
    示例: R03 → [3, 6, 9, ..., 240]  FOG → [3, 6, 9, ..., 72]
    """
    max_hour = get_max_forecast_hour(var)
    return list(range(FORECAST_INTERVAL, max_hour + 1, FORECAST_INTERVAL))


# 12h时段总数（240h / 12 = 20段）
MAX_SEGMENTS: int = MAX_FORECAST_HOUR_240 // 12


def get_segment_fh(seg_idx: int) -> list[int]:
    """
    获取第 seg_idx 个12h时段对应的4个预报时效（逐3小时）
    seg_idx 从 1 开始
    示例：seg_idx=1 → [3, 6, 9, 12]; seg_idx=2 → [15, 18, 21, 24]

    纯算法函数，不涉及任何文件I/O，供 cli（数据加载）与 src（结果保存/日志）共同引用。
    """
    base = (seg_idx - 1) * 12
    return [base + 3, base + 6, base + 9, base + 12]
