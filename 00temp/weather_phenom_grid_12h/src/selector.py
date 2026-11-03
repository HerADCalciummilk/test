# -*- coding: utf-8 -*-
"""
天气现象选取模块（流程图左侧）
依据 QX/T 740-2024 第4章：
  1. 选取12h内影响级最高的天气现象A
  2. 选取第2个影响级较高的天气现象B（需非互斥且有独立出现时间）
  3. 若无合适B则为单一天气现象A

性能优化：全程使用 int8 索引运算，避免 dtype=object 字符串比较
"""
import numpy as np

from resource.weather_config import WEATHER_INFLUENCE_LEVEL, is_mutually_exclusive

# 按影响级从高到低排列的电码列表（影响级数字越小，优先级越高）
SORTED_CODES = sorted(
    WEATHER_INFLUENCE_LEVEL.keys(),
    key=lambda c: WEATHER_INFLUENCE_LEVEL[c]
)
N_CODES = len(SORTED_CODES)
CODE_TO_IDX = {c: i for i, c in enumerate(SORTED_CODES)}

# 预计算互斥矩阵 [N_CODES, N_CODES] bool
_EXCL = np.zeros((N_CODES, N_CODES), dtype=bool)
for _i, _ca in enumerate(SORTED_CODES):
    for _j, _cb in enumerate(SORTED_CODES):
        _EXCL[_i, _j] = is_mutually_exclusive(_ca, _cb)

# 预计算每个 a_idx 的有效 b_idx 候选列表（非自身、非互斥）
_VALID_B_FOR_A = []
for _a in range(N_CODES):
    _VALID_B_FOR_A.append(
        [_b for _b in range(N_CODES) if _b != _a and not _EXCL[_a, _b]]
    )


def select(occur: dict[str, dict[str, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """
    为每个网格点选取天气现象A和B

    Args:
        occur: identify() 的输出，{电码: {"12h": [lat,lon] bool, "fine": [4,lat,lon] bool}}

    Returns:
        idx_A : ndarray[lat, lon] int8  — 天气现象A在SORTED_CODES中的索引
        idx_B : ndarray[lat, lon] int8  — 天气现象B的索引，无B时为 -1
    """
    # 获取网格形状
    ref_12h = next(iter(occur.values()))["12h"]
    shape = ref_12h.shape   # (nlat, nlon)

    # ── 构建出现矩阵 [N_CODES, lat, lon] ────────────────────
    present = np.stack(
        [occur[c]["12h"].astype(bool) for c in SORTED_CODES],
        axis=0
    )   # shape: [31, nlat, nlon]

    # ── 选取A：第一个出现的（影响级最高）────────────────────
    any_present = present.any(axis=0)               # [lat, lon] bool
    idx_A = np.argmax(present, axis=0).astype(np.int8)  # [lat, lon] int8

    # 兜底：无任何现象时 → 晴(00)
    fallback_idx = np.int8(CODE_TO_IDX["00"])
    idx_A = np.where(any_present, idx_A, fallback_idx)

    # ── 预提取所有 fine 数组 [N_CODES, n_steps, lat, lon] ──
    fine_all = np.stack(
        [occur[c]["fine"].astype(bool) for c in SORTED_CODES],
        axis=0
    )   # shape: [31, 4, nlat, nlon]

    # ── 选取B（全 int8 运算）────────────────────────────────
    idx_B = np.full(shape, -1, dtype=np.int8)
    b_assigned = np.zeros(shape, dtype=bool)   # 替代 code_B == "" 的字符串比较

    for a_idx in range(N_CODES):
        mask_a = (idx_A == a_idx)
        if not np.any(mask_a):
            continue

        fine_a = fine_all[a_idx]                     # [4, lat, lon]
        # 一次性计算所有 b_code 的 has_independent
        has_indep_all = np.any(fine_all & ~fine_a, axis=1)  # [31, lat, lon]

        # 只遍历非互斥的有效 B 候选
        for b_idx in _VALID_B_FOR_A[a_idx]:
            # 剪枝：该B在整个网格内都未出现，跳过
            if not np.any(present[b_idx]):
                continue
            # B在12h内出现 且 存在独立出现时间 且 B尚未确定
            can_be_b = mask_a & present[b_idx] & has_indep_all[b_idx] & ~b_assigned
            if np.any(can_be_b):
                idx_B[can_be_b] = np.int8(b_idx)
                b_assigned |= can_be_b

    return idx_A, idx_B


# ══════════════════════════════════════════════════════════════
# 算法插件 (Plugin) — DIA 诊断类
# ══════════════════════════════════════════════════════════════

class DIA_WeatherPhenomSelector:
    """
    天气现象选取算法插件 (DIA - Diagnostic)

    依据 QX/T 740-2024 第4章，为每个网格点从31种候选天气现象中选取
    影响级最高的A现象与独立出现的B现象（无合适B时仅返回A）。

    设计规范：
      - 严禁文件 I/O；输入输出均为内存对象 (ndarray / dict)
      - 环境无关：影响级与互斥关系通过 __init__ 显式注入，无隐藏全局依赖
      - 向量化计算：预计算互斥矩阵，批量 int8 索引运算

    Args:
        config (dict | None): 可选配置字典，用于覆盖默认值。
            支持的键：WEATHER_INFLUENCE_LEVEL (dict)
            None 表示使用 resource.weather_config 标准配置（推荐）。

    Example:
        >>> plugin = DIA_WeatherPhenomSelector()
        >>> idx_A, idx_B = plugin.process(occur)
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config   # 预留：自定义天气现象配置注入钩子

    def process(self, occur: dict) -> tuple:
        """
        为每个网格点选取天气现象A和B。

        Args:
            occur (dict): DIA_WeatherPhenomIdentifier.process() 的输出。
                格式：{电码(str): {"12h": ndarray[lat, lon] bool,
                                   "fine": ndarray[4, lat, lon] bool}}

        Returns:
            tuple:
                - idx_A (ndarray[lat, lon] int8): 天气现象A在SORTED_CODES中的索引
                - idx_B (ndarray[lat, lon] int8): 天气现象B的索引，无B时为 -1
        """
        return select(occur)
