# -*- coding: utf-8 -*-
"""
单元测试 - 逻辑关系判断模块
验证 judge() 对"转"/"间"/"伴有"/单一的判断逻辑
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.logic_judger import judge
from src.selector import SORTED_CODES, CODE_TO_IDX
from resource.weather_config import WEATHER_INFLUENCE_LEVEL

# 统一网格
N_STEPS, NLAT, NLON = 4, 3, 4
SHAPE = (NLAT, NLON)
FINE_SHAPE = (N_STEPS, NLAT, NLON)


def _make_occur(fine_patterns=None):
    """
    构造 occur 字典（所有现象12h都出现，fine按指定模式）
    fine_patterns: dict {code: [4, nlat, nlon] bool}
    """
    occur = {}
    for code in WEATHER_INFLUENCE_LEVEL:
        if fine_patterns and code in fine_patterns:
            fine = fine_patterns[code]
        else:
            fine = np.zeros(FINE_SHAPE, dtype=bool)
        occur[code] = {
            "12h": np.full(SHAPE, True, dtype=bool),
            "fine": fine,
        }
    return occur


# ══════════════════════════════════════════════════════════
# 一、单一天气现象 (logic=0)
# ══════════════════════════════════════════════════════════
def test_single_no_B():
    """idx_B=-1 → logic=0, final_A=final_B=A"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["01"], dtype=np.int8)  # 多云
    idx_B = np.full(SHAPE, -1, dtype=np.int8)
    occur = _make_occur()

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 0), "无B时 logic 应全为0(单一)"
    assert np.all(fa == idx_A), "单一时 final_A = idx_A"
    assert np.all(fb == idx_A), "单一时 final_B = idx_A"
    print("  [PASS] test_single_no_B: 单一现象→logic=0")


# ══════════════════════════════════════════════════════════
# 二、"转"逻辑 (logic=1)
# ══════════════════════════════════════════════════════════
def test_zhuan_basic():
    """大雨+大雾(非伴有/非间候选) → "转"(logic=1)，先出现的在前"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["09"], dtype=np.int8)  # 大雨
    idx_B = np.full(SHAPE, CODE_TO_IDX["62"], dtype=np.int8)  # 大雾

    # fine: 大雨先出现(step0)，大雾后出现(step2)
    fine_09 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_09[0] = True
    fine_62 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_62[2] = True
    occur = _make_occur({"09": fine_09, "62": fine_62})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 1), "大雨+大雾应为'转'(logic=1)"
    # 大雨先出现 → final_A=大雨
    assert np.all(fa == CODE_TO_IDX["09"]), "先出现的大雨应在前"
    assert np.all(fb == CODE_TO_IDX["62"]), "后出现的大雾应在后"
    print("  [PASS] test_zhuan_basic: 大雨转大雾")


def test_zhuan_reverse_order():
    """B先出现 → final_A=B, final_B=A（表述顺序按首次出现）"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["09"], dtype=np.int8)  # 大雨
    idx_B = np.full(SHAPE, CODE_TO_IDX["62"], dtype=np.int8)  # 大雾

    # fine: 大雾先出现(step0)，大雨后出现(step2)
    fine_62 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_62[0] = True
    fine_09 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_09[2] = True
    occur = _make_occur({"09": fine_09, "62": fine_62})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 1), "仍为'转'"
    # 大雾先出现 → final_A=大雾
    assert np.all(fa == CODE_TO_IDX["62"]), "先出现的大雾应在前"
    assert np.all(fb == CODE_TO_IDX["09"]), "后出现的大雨应在后"
    print("  [PASS] test_zhuan_reverse_order: 大雾转大雨（B先出现）")


# ══════════════════════════════════════════════════════════
# 三、"伴有"逻辑 (logic=3)
# ══════════════════════════════════════════════════════════
def test_accompany_fog_haze():
    """大雾(62)+轻度霾(55) → "伴有"(logic=3)，影响级高的在前"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["62"], dtype=np.int8)  # 大雾 lv=23
    idx_B = np.full(SHAPE, CODE_TO_IDX["55"], dtype=np.int8)  # 轻度霾 lv=27

    fine_62 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_62[0] = True
    fine_55 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_55[1] = True
    occur = _make_occur({"62": fine_62, "55": fine_55})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 3), "雾+霾应为'伴有'(logic=3)"
    # 大雾影响级更高(23 < 27)，应在前
    assert np.all(fa == CODE_TO_IDX["62"]), "大雾影响级高应在前"
    assert np.all(fb == CODE_TO_IDX["55"]), "轻度霾应在后"
    print("  [PASS] test_accompany_fog_haze: 大雾伴有轻度霾")


def test_accompany_reverse():
    """轻度霾(55)+浓雾(63) → 伴有，浓雾影响级更高 → 浓雾在前"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["55"], dtype=np.int8)  # 轻度霾 lv=27
    idx_B = np.full(SHAPE, CODE_TO_IDX["63"], dtype=np.int8)  # 浓雾 lv=16

    fine_55 = np.full(FINE_SHAPE, True, dtype=bool)
    fine_63 = np.full(FINE_SHAPE, True, dtype=bool)
    occur = _make_occur({"55": fine_55, "63": fine_63})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 3), "霾+雾应为'伴有'"
    # 浓雾影响级更高(16 < 27)
    assert np.all(fa == CODE_TO_IDX["63"]), "浓雾影响级高应在前"
    assert np.all(fb == CODE_TO_IDX["55"]), "轻度霾应在后"
    print("  [PASS] test_accompany_reverse: 浓雾伴有轻度霾（调整顺序）")


# ══════════════════════════════════════════════════════════
# 四、"间"逻辑 (logic=2)
# ══════════════════════════════════════════════════════════
def test_jian_alternating():
    """晴(00)+多云(01)交替出现 → "间"(logic=2)"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["01"], dtype=np.int8)  # 多云
    idx_B = np.full(SHAPE, CODE_TO_IDX["00"], dtype=np.int8)  # 晴

    # 交替出现：step0,2=多云; step1,3=晴
    fine_01 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_01[0] = True
    fine_01[2] = True
    fine_00 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_00[1] = True
    fine_00[3] = True
    occur = _make_occur({"01": fine_01, "00": fine_00})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert np.all(logic == 2), "晴/多云交替应为'间'(logic=2)"
    print("  [PASS] test_jian_alternating: 多云间晴")


def test_jian_no_alternate_fallback_zhuan():
    """晴+多云但不交替(同时出现) → 降级为转"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["01"], dtype=np.int8)  # 多云
    idx_B = np.full(SHAPE, CODE_TO_IDX["00"], dtype=np.int8)  # 晴

    # 不交替：step0同时出现晴和多云
    fine_01 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_01[0] = True
    fine_01[1] = True
    fine_00 = np.zeros(FINE_SHAPE, dtype=bool)
    fine_00[0] = True  # 与多云重叠
    fine_00[1] = True  # 与多云重叠
    # 无B单独出现的时段 → 不满足交替条件
    occur = _make_occur({"01": fine_01, "00": fine_00})

    logic, fa, fb = judge(idx_A, idx_B, occur)

    # 无B单独出现 → 不交替 → 降级为"转"
    assert np.all(logic == 1), "不交替时应降级为'转'(logic=1)"
    print("  [PASS] test_jian_no_alternate_fallback_zhuan: 不交替→转")


# ══════════════════════════════════════════════════════════
# 五、输出格式测试
# ══════════════════════════════════════════════════════════
def test_output_dtype():
    """输出全部为int8"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["01"], dtype=np.int8)
    idx_B = np.full(SHAPE, -1, dtype=np.int8)
    occur = _make_occur()

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert logic.dtype == np.int8, f"logic dtype 应为 int8"
    assert fa.dtype == np.int8, f"fa dtype 应为 int8"
    assert fb.dtype == np.int8, f"fb dtype 应为 int8"
    print("  [PASS] test_output_dtype: 输出全为int8")


def test_output_shape():
    """输出 shape 应与输入一致"""
    idx_A = np.full(SHAPE, CODE_TO_IDX["01"], dtype=np.int8)
    idx_B = np.full(SHAPE, -1, dtype=np.int8)
    occur = _make_occur()

    logic, fa, fb = judge(idx_A, idx_B, occur)

    assert logic.shape == SHAPE
    assert fa.shape == SHAPE
    assert fb.shape == SHAPE
    print("  [PASS] test_output_shape: 输出shape正确")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== 逻辑关系判断模块单元测试 ===")
    # 单一
    test_single_no_B()
    # 转
    test_zhuan_basic()
    test_zhuan_reverse_order()
    # 伴有
    test_accompany_fog_haze()
    test_accompany_reverse()
    # 间
    test_jian_alternating()
    test_jian_no_alternate_fallback_zhuan()
    # 输出格式
    test_output_dtype()
    test_output_shape()
    print("\n全部通过!")
