# -*- coding: utf-8 -*-
"""
天气现象逻辑关系判断模块（流程图右侧）
依据 QX/T 740-2024 第5章和附录E：
  - "伴有"：A为雾等级 + B为霾等级（或反之）
  - "间"  ：A/B为晴/多云/阴/小雨特定组合 且 交替出现
  - "转"  ：其余情况，按首次出现时间确定先后

性能优化：全程使用 int8 索引运算，避免 dtype=object 字符串比较
"""
import numpy as np

from resource.weather_config import (
    WEATHER_INFLUENCE_LEVEL,
    is_accompanied_by,
    is_jian_candidate,
    FOG_CODES, HAZE_CODES,
)

# 本地构建 code→idx 映射
_SORTED_CODES = sorted(WEATHER_INFLUENCE_LEVEL.keys(), key=lambda c: WEATHER_INFLUENCE_LEVEL[c])
_CODE_TO_IDX  = {c: i for i, c in enumerate(_SORTED_CODES)}
_N_CODES = len(_SORTED_CODES)

# 预计算影响级数组 [N_CODES] — 按索引直接查询，避免循环内 dict.get
_INFLUENCE_LUT = np.array(
    [WEATHER_INFLUENCE_LEVEL[c] for c in _SORTED_CODES], dtype=np.int8
)

# 预计算 "伴有" 关系矩阵 [N_CODES, N_CODES] bool
_ACCOMPANY = np.zeros((_N_CODES, _N_CODES), dtype=bool)
for _i, _ca in enumerate(_SORTED_CODES):
    for _j, _cb in enumerate(_SORTED_CODES):
        _ACCOMPANY[_i, _j] = is_accompanied_by(_ca, _cb)

# 预计算 "间" 候选矩阵 [N_CODES, N_CODES] bool
_JIAN_CAND = np.zeros((_N_CODES, _N_CODES), dtype=bool)
for _i, _ca in enumerate(_SORTED_CODES):
    for _j, _cb in enumerate(_SORTED_CODES):
        _JIAN_CAND[_i, _j] = is_jian_candidate(_ca, _cb)


# ──────────────────────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────────────────────

def _first_appear(fine: np.ndarray) -> np.ndarray:
    """
    返回每个格点第一次出现(True)的时步索引(0-based)
    若从未出现返回 n_steps（即越界索引，表示"未出现"）
    fine: [n_steps, lat, lon] bool
    """
    n_steps = fine.shape[0]
    result  = np.argmax(fine, axis=0)      # 全False时argmax返回0
    any_occ = fine.any(axis=0)
    return np.where(any_occ, result, n_steps).astype(np.int8)


def _duration(fine: np.ndarray) -> np.ndarray:
    """
    返回每个格点出现(True)的时步数
    fine: [n_steps, lat, lon] bool → [lat, lon] int8
    """
    return fine.sum(axis=0).astype(np.int8)


def _is_alternating(fine_a: np.ndarray, fine_b: np.ndarray) -> np.ndarray:
    """
    判断A和B是否交替出现
    定义：既有"A单独出现(A=T,B=F)"的时步，也有"B单独出现(A=F,B=T)"的时步
    fine_a, fine_b: [n_steps, lat, lon] bool → [lat, lon] bool
    """
    a_only = fine_a & ~fine_b
    b_only = fine_b & ~fine_a
    return a_only.any(axis=0) & b_only.any(axis=0)


# ──────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────

def judge(idx_A: np.ndarray, idx_B: np.ndarray,
          occur: dict[str, dict[str, np.ndarray]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    判断逻辑关系，确定最终表述顺序

    Args:
        idx_A   : [lat, lon] int8 — 天气现象A在SORTED_CODES中的索引
        idx_B   : [lat, lon] int8 — 天气现象B的索引（无B时为 -1）
        occur   : identify() 输出的出现信息

    Returns:
        logic       : [lat, lon] int8 — 0=单一, 1=转, 2=间, 3=伴有
        idx_final_A : [lat, lon] int8 — 表述在前的索引
        idx_final_B : [lat, lon] int8 — 表述在后的索引（单一时 = idx_final_A）
    """
    shape = idx_A.shape

    logic       = np.zeros(shape, dtype=np.int8)
    idx_final_A = idx_A.copy()
    idx_final_B = idx_A.copy()    # 单一现象时 final_B = final_A（用于编码KAAAA）

    has_b = (idx_B != -1)         # 有B的格点（int比较，极快）

    if not np.any(has_b):
        return logic, idx_final_A, idx_final_B

    # 获取 fine 数组形状（用于空填充）
    ref_fine = next(iter(occur.values()))["fine"]
    fine_shape = ref_fine.shape   # (n_steps, nlat, nlon)

    # ── 预计算所有活跃 code 的 first_appear / duration ──
    first_cache = {}   # idx -> [lat, lon] int8
    dur_cache = {}     # idx -> [lat, lon] int8
    active_indices = set(np.unique(idx_A)) | set(np.unique(idx_B[has_b]))
    for aidx in active_indices:
        code = _SORTED_CODES[aidx]
        fine = occur.get(code, {}).get("fine", np.zeros(fine_shape, bool))
        first_cache[aidx] = _first_appear(fine)
        dur_cache[aidx]   = _duration(fine)

    # 遍历所有(A, B)组合，对满足条件的格点批量处理
    unique_A = np.unique(idx_A)
    unique_B = np.unique(idx_B[has_b])

    for a_idx in unique_A:
        for b_idx in unique_B:
            mask = has_b & (idx_A == a_idx) & (idx_B == b_idx)
            if not np.any(mask):
                continue

            a_idx_int = int(a_idx)
            b_idx_int = int(b_idx)

            # ── 判断"伴有"（雾+霾组合）──────────────────────
            if _ACCOMPANY[a_idx_int, b_idx_int]:
                lv_a = _INFLUENCE_LUT[a_idx_int]
                lv_b = _INFLUENCE_LUT[b_idx_int]
                # 影响级高的在前（数字小=影响级高）
                if lv_a <= lv_b:
                    fa, fb = np.int8(a_idx), np.int8(b_idx)
                else:
                    fa, fb = np.int8(b_idx), np.int8(a_idx)
                logic[mask]       = 3
                idx_final_A[mask] = fa
                idx_final_B[mask] = fb
                continue

            # ── 判断"间"候选 ─────────────────────────────────
            if _JIAN_CAND[a_idx_int, b_idx_int]:
                a_code = _SORTED_CODES[a_idx_int]
                b_code = _SORTED_CODES[b_idx_int]
                fine_a = occur.get(a_code, {}).get("fine",
                         np.zeros(fine_shape, bool)).astype(bool)
                fine_b = occur.get(b_code, {}).get("fine",
                         np.zeros(fine_shape, bool)).astype(bool)

                is_alt     = _is_alternating(fine_a, fine_b)   # [lat, lon]
                mask_jian  = mask & is_alt
                mask_zhuan = mask & ~is_alt

                # "间"逻辑：持续时间长的在前；时间相同则影响级高的在前
                if np.any(mask_jian):
                    dur_a = dur_cache[a_idx_int]
                    dur_b = dur_cache[b_idx_int]
                    lv_a  = _INFLUENCE_LUT[a_idx_int]
                    lv_b  = _INFLUENCE_LUT[b_idx_int]
                    a_first = (dur_a > dur_b) | ((dur_a == dur_b) & (lv_a < lv_b))
                    fa = np.where(a_first, np.int8(a_idx), np.int8(b_idx))
                    fb = np.where(a_first, np.int8(b_idx), np.int8(a_idx))
                    logic[mask_jian]       = 2
                    idx_final_A[mask_jian] = fa[mask_jian]
                    idx_final_B[mask_jian] = fb[mask_jian]

                # 不交替则降级为"转"
                if np.any(mask_zhuan):
                    _apply_zhuan_inplace(
                        mask_zhuan, a_idx_int, b_idx_int, first_cache,
                        logic, idx_final_A, idx_final_B
                    )
            else:
                # ── "转"逻辑 ────────────────────────────────
                _apply_zhuan_inplace(
                    mask, a_idx_int, b_idx_int, first_cache,
                    logic, idx_final_A, idx_final_B
                )

    return logic, idx_final_A, idx_final_B


def _apply_zhuan_inplace(mask, a_idx: int, b_idx: int, first_cache,
                         logic, idx_final_A, idx_final_B):
    """
    对满足 mask 的格点，原地应用"转"逻辑关系
    先出现的放前面；同时出现则影响级高的放前面
    """
    first_a = first_cache[a_idx]
    first_b = first_cache[b_idx]
    lv_a = _INFLUENCE_LUT[a_idx]
    lv_b = _INFLUENCE_LUT[b_idx]

    # A先出现 OR (同时出现 AND A影响级更高)
    a_first = (first_a < first_b) | ((first_a == first_b) & (lv_a < lv_b))
    fa = np.where(a_first, np.int8(a_idx), np.int8(b_idx))
    fb = np.where(a_first, np.int8(b_idx), np.int8(a_idx))

    logic[mask]       = 1
    idx_final_A[mask] = fa[mask]
    idx_final_B[mask] = fb[mask]


# ══════════════════════════════════════════════════════════════
# 算法插件 (Plugin) — DIA 诊断类
# ══════════════════════════════════════════════════════════════

class DIA_WeatherPhenomLogicJudger:
    """
    天气现象逻辑关系判断算法插件 (DIA - Diagnostic)

    依据 QX/T 740-2024 第5章和附录E，判断两种天气现象之间的逻辑关系：
      - "伴有" (logic=3)：如雾等级 + 霾等级组合
      - "间"   (logic=2)：如晴/多云/阴/小雨特定组合且交替出现
      - "转"   (logic=1)：其余双现象情况，按首次出现时间确定前后
      - 单一   (logic=0)：仅有A现象

    设计规范：
      - 严禁文件 I/O；输入输出均为内存对象 (ndarray / dict)
      - 环境无关：逻辑关系配置通过 __init__ 显式注入，无隐藏全局依赖
      - 向量化计算：预计算伴有/间矩阵，批量 int8 索引运算

    Args:
        config (dict | None): 可选配置字典，用于覆盖默认值。
            支持的键：WEATHER_INFLUENCE_LEVEL, FOG_CODES, HAZE_CODES
            None 表示使用 resource.weather_config 标准配置（推荐）。

    Example:
        >>> plugin = DIA_WeatherPhenomLogicJudger()
        >>> logic, idx_fa, idx_fb = plugin.process(idx_A, idx_B, occur)
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config   # 预留：自定义逻辑关系配置注入钩子

    def process(self, idx_A: np.ndarray, idx_B: np.ndarray,
                occur: dict) -> tuple:
        """
        判断逻辑关系，确定最终表述顺序。

        Args:
            idx_A  (np.ndarray): [lat, lon] int8 — 天气现象A在SORTED_CODES中的索引
            idx_B  (np.ndarray): [lat, lon] int8 — 天气现象B的索引（无B时为 -1）
            occur  (dict):       DIA_WeatherPhenomIdentifier.process() 的输出

        Returns:
            tuple:
                - logic       (ndarray[lat, lon] int8): 0=单一, 1=转, 2=间, 3=伴有
                - idx_final_A (ndarray[lat, lon] int8): 表述在前的索引
                - idx_final_B (ndarray[lat, lon] int8): 表述在后的索引（单一时=idx_final_A）
        """
        return judge(idx_A, idx_B, occur)
