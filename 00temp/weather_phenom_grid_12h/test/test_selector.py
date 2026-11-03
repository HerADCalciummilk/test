# -*- coding: utf-8 -*-
"""
单元测试 - 天气现象选取模块
验证 select() 的A/B选取逻辑
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.selector import select, SORTED_CODES, CODE_TO_IDX, N_CODES
from resource.weather_config import WEATHER_INFLUENCE_LEVEL

# 统一网格
N_STEPS, NLAT, NLON = 4, 3, 4
SHAPE = (NLAT, NLON)
FINE_SHAPE = (N_STEPS, NLAT, NLON)


def _make_occur(present_codes, fine_patterns=None):
    """
    构造 occur 字典
    Args:
        present_codes: list of str，12h内出现的电码（整个网格都出现）
        fine_patterns: dict {code: [4, nlat, nlon] bool}，精细时步模式
                       未指定时默认全时步出现
    Returns:
        occur dict
    """
    occur = {}
    for code in WEATHER_INFLUENCE_LEVEL:
        is_present = code in present_codes
        if fine_patterns and code in fine_patterns:
            fine = fine_patterns[code]
        else:
            fine = np.full(FINE_SHAPE, is_present, dtype=bool)
        occur[code] = {
            "12h": np.full(SHAPE, is_present, dtype=bool),
            "fine": fine,
        }
    return occur


# ══════════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════════
def test_single_phenomenon():
    """只有一种现象出现 → A=该现象，B=-1"""
    occur = _make_occur(["01"])  # 只有多云
    idx_A, idx_B = select(occur)

    expected_idx = CODE_TO_IDX["01"]
    assert np.all(idx_A == expected_idx), f"A应为多云(idx={expected_idx})"
    assert np.all(idx_B == -1), "只有一种现象时B应为-1"
    print("  [PASS] test_single_phenomenon: 多云→A=多云, B=-1")


def test_highest_influence():
    """多种现象出现 → A=影响级最高的"""
    # 大雨(09, lv=10) + 小雨(07, lv=26) → A应为大雨
    occur = _make_occur(["09", "07"])
    idx_A, idx_B = select(occur)

    assert np.all(idx_A == CODE_TO_IDX["09"]), "A应为大雨(影响级更高)"
    print("  [PASS] test_highest_influence: 大雨优先级高于小雨")


def test_mutual_exclusive_no_B():
    """互斥现象不可同时作为A和B"""
    # 大雨(09)和中雨(08)互斥（都属于降雨类）
    # fine: 大雨全时段出现，中雨也全时段出现（但互斥不选B）
    occur = _make_occur(["09", "08"])
    idx_A, idx_B = select(occur)

    # A=大雨（影响级更高），B不能是中雨（互斥）
    assert np.all(idx_A == CODE_TO_IDX["09"]), "A应为大雨"
    # B应为-1（因为没有其他非互斥现象）
    assert np.all(idx_B == -1), "互斥现象不能作为B"
    print("  [PASS] test_mutual_exclusive_no_B: 互斥现象不能同为A、B")


def test_dual_non_exclusive():
    """非互斥且有独立时间 → 选取B"""
    # 大雨(09, 降雨类) + 大雾(62, 雾类) → 非互斥
    # 大雨前2步出现，大雾后2步出现（有独立时间）
    fine_09 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_09[:2] = True
    fine_62 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_62[2:] = True

    occur = _make_occur(["09", "62"], fine_patterns={"09": fine_09, "62": fine_62})
    idx_A, idx_B = select(occur)

    assert np.all(idx_A == CODE_TO_IDX["09"]), "A应为大雨(影响级更高)"
    assert np.all(idx_B == CODE_TO_IDX["62"]), "B应为大雾(非互斥+有独立时间)"
    print("  [PASS] test_dual_non_exclusive: 大雨+大雾→A=大雨,B=大雾")


def test_no_independent_time_no_B():
    """非互斥但无独立出现时间 → 不选B"""
    # 阴(02) + 多云(01) → 非互斥
    # 但两者完全重叠（同时步出现），无独立时间
    fine_same = np.zeros(FINE_SHAPE, dtype=bool)
    fine_same[:2] = True  # 两者完全相同时段
    occur = _make_occur(["02", "01"], fine_patterns={"02": fine_same, "01": fine_same})
    idx_A, idx_B = select(occur)

    assert np.all(idx_A == CODE_TO_IDX["02"]), "A应为阴(影响级更高)"
    assert np.all(idx_B == -1), "无独立时间不应选B"
    print("  [PASS] test_no_independent_time_no_B: 无独立时间→不选B")


def test_fallback_qing():
    """无任何现象出现 → 兜底为晴(00)"""
    occur = _make_occur([])  # 什么都不出现
    idx_A, idx_B = select(occur)

    assert np.all(idx_A == CODE_TO_IDX["00"]), "无现象时A应为晴(兜底)"
    assert np.all(idx_B == -1), "无现象时B应为-1"
    print("  [PASS] test_fallback_qing: 无现象→兜底为晴")


def test_output_dtype():
    """输出应为 int8 类型"""
    occur = _make_occur(["01"])
    idx_A, idx_B = select(occur)

    assert idx_A.dtype == np.int8, f"idx_A dtype 应为 int8，得到 {idx_A.dtype}"
    assert idx_B.dtype == np.int8, f"idx_B dtype 应为 int8，得到 {idx_B.dtype}"
    print("  [PASS] test_output_dtype: 输出为int8")


def test_output_shape():
    """输出 shape 应为 (nlat, nlon)"""
    occur = _make_occur(["01"])
    idx_A, idx_B = select(occur)

    assert idx_A.shape == SHAPE, f"idx_A shape 应为 {SHAPE}"
    assert idx_B.shape == SHAPE, f"idx_B shape 应为 {SHAPE}"
    print("  [PASS] test_output_shape: 输出shape正确")


def test_mixed_grid():
    """不同格点有不同现象 → 各格点独立选取"""
    occur = {}
    for code in WEATHER_INFLUENCE_LEVEL:
        occur[code] = {
            "12h": np.zeros(SHAPE, dtype=bool),
            "fine": np.zeros(FINE_SHAPE, dtype=bool),
        }
    # 格点(0,0)只有多云
    occur["01"]["12h"][0, 0] = True
    occur["01"]["fine"][:, 0, 0] = True
    # 格点(1,1)只有大雨
    occur["09"]["12h"][1, 1] = True
    occur["09"]["fine"][:, 1, 1] = True

    idx_A, idx_B = select(occur)

    assert idx_A[0, 0] == CODE_TO_IDX["01"], "格点(0,0)应为多云"
    assert idx_A[1, 1] == CODE_TO_IDX["09"], "格点(1,1)应为大雨"
    # 无B
    assert idx_B[0, 0] == -1
    assert idx_B[1, 1] == -1
    print("  [PASS] test_mixed_grid: 不同格点独立选取")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== 天气现象选取模块单元测试 ===")
    test_single_phenomenon()
    test_highest_influence()
    test_mutual_exclusive_no_B()
    test_dual_non_exclusive()
    test_no_independent_time_no_B()
    test_fallback_qing()
    test_output_dtype()
    test_output_shape()
    test_mixed_grid()
    print("\n全部通过!")
