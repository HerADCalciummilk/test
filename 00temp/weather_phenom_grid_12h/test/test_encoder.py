# -*- coding: utf-8 -*-
"""
单元测试 - 编码器模块
验证 encode/decode 的正确性（覆盖所有逻辑关系类型和边界情况）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.encoder import encode, decode
from src.selector import SORTED_CODES, CODE_TO_IDX


# ══════════════════════════════════════════════════════════
# 一、单一天气现象编码 (K=0)
# ══════════════════════════════════════════════════════════
def test_encode_single_duoyun():
    """单一多云(01) → 00101"""
    idx = np.int8(CODE_TO_IDX["01"])
    idx_A = np.array([[idx]], dtype=np.int8)
    idx_B = np.array([[idx]], dtype=np.int8)
    logic = np.array([[0]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 101, f"期望 00101, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_single_duoyun: 多云→00101")


def test_encode_single_qing():
    """单一晴(00) → 00000"""
    idx = np.int8(CODE_TO_IDX["00"])
    idx_A = np.array([[idx]], dtype=np.int8)
    idx_B = np.array([[idx]], dtype=np.int8)
    logic = np.array([[0]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 0, f"期望 00000, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_single_qing: 晴→00000")


def test_encode_single_baoyu():
    """单一暴雨(10) → 01010"""
    idx = np.int8(CODE_TO_IDX["10"])
    idx_A = np.array([[idx]], dtype=np.int8)
    idx_B = np.array([[idx]], dtype=np.int8)
    logic = np.array([[0]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 1010, f"期望 01010, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_single_baoyu: 暴雨→01010")


# ══════════════════════════════════════════════════════════
# 二、"转"编码 (K=1)
# ══════════════════════════════════════════════════════════
def test_encode_zhuan():
    """阴(02)转小雨(07) → 10207"""
    idx_yin = np.int8(CODE_TO_IDX["02"])
    idx_rain = np.int8(CODE_TO_IDX["07"])
    idx_A = np.array([[idx_yin]], dtype=np.int8)
    idx_B = np.array([[idx_rain]], dtype=np.int8)
    logic = np.array([[1]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 10207, f"期望 10207, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_zhuan: 阴转小雨→10207")


def test_encode_zhuan_rain_to_snow():
    """中雨(08)转小雪(14) → 10814"""
    idx_A = np.array([[np.int8(CODE_TO_IDX["08"])]], dtype=np.int8)
    idx_B = np.array([[np.int8(CODE_TO_IDX["14"])]], dtype=np.int8)
    logic = np.array([[1]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 10814, f"期望 10814, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_zhuan_rain_to_snow: 中雨转小雪→10814")


# ══════════════════════════════════════════════════════════
# 三、"间"编码 (K=2)
# ══════════════════════════════════════════════════════════
def test_encode_jian():
    """晴(00)间多云(01) → 20001"""
    idx_qing = np.int8(CODE_TO_IDX["00"])
    idx_duoyun = np.int8(CODE_TO_IDX["01"])
    idx_A = np.array([[idx_qing]], dtype=np.int8)
    idx_B = np.array([[idx_duoyun]], dtype=np.int8)
    logic = np.array([[2]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 20001, f"期望 20001, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_jian: 晴间多云→20001")


def test_encode_jian_yin_xiaoyu():
    """阴(02)间小雨(07) → 20207"""
    idx_A = np.array([[np.int8(CODE_TO_IDX["02"])]], dtype=np.int8)
    idx_B = np.array([[np.int8(CODE_TO_IDX["07"])]], dtype=np.int8)
    logic = np.array([[2]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 20207, f"期望 20207, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_jian_yin_xiaoyu: 阴间小雨→20207")


# ══════════════════════════════════════════════════════════
# 四、"伴有"编码 (K=3)
# ══════════════════════════════════════════════════════════
def test_encode_accompany():
    """中度霾(56)伴有轻雾(61) → 35661"""
    idx_haze = np.int8(CODE_TO_IDX["56"])
    idx_fog = np.int8(CODE_TO_IDX["61"])
    idx_A = np.array([[idx_haze]], dtype=np.int8)
    idx_B = np.array([[idx_fog]], dtype=np.int8)
    logic = np.array([[3]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result[0, 0] == 35661, f"期望 35661, 得到 {result[0,0]:05d}"
    print("  [PASS] test_encode_accompany: 中度霾伴有轻雾→35661")


# ══════════════════════════════════════════════════════════
# 五、decode 解码测试
# ══════════════════════════════════════════════════════════
def test_decode_single():
    """解码 00101 → 多云"""
    info = decode(101)
    assert info["逻辑关系电码"] == 0
    assert info["天气现象A电码"] == "01"
    assert info["天气现象B电码"] == "01"
    assert info["预报表述"] == "多云"
    print("  [PASS] test_decode_single: 00101→多云")


def test_decode_zhuan():
    """解码 10207 → 阴转小雨"""
    info = decode(10207)
    assert info["逻辑关系电码"] == 1
    assert info["逻辑关系"] == "转"
    assert info["天气现象A电码"] == "02"
    assert info["天气现象B电码"] == "07"
    assert info["预报表述"] == "阴转小雨"
    print("  [PASS] test_decode_zhuan: 10207→阴转小雨")


def test_decode_jian():
    """解码 20001 → 晴间多云"""
    info = decode(20001)
    assert info["逻辑关系电码"] == 2
    assert info["逻辑关系"] == "间"
    assert info["天气现象A电码"] == "00"
    assert info["天气现象B电码"] == "01"
    assert info["预报表述"] == "晴间多云"
    print("  [PASS] test_decode_jian: 20001→晴间多云")


def test_decode_accompany():
    """解码 35661 → 中度霾伴有轻雾"""
    info = decode(35661)
    assert info["逻辑关系电码"] == 3
    assert info["逻辑关系"] == "伴有"
    assert info["天气现象A电码"] == "56"
    assert info["天气现象B电码"] == "61"
    assert info["预报表述"] == "中度霾伴有轻雾"
    print("  [PASS] test_decode_accompany: 35661→中度霾伴有轻雾")


# ══════════════════════════════════════════════════════════
# 六、批量编码（多格点）
# ══════════════════════════════════════════════════════════
def test_encode_batch():
    """2x2网格，混合逻辑关系"""
    idx_A = np.array([
        [CODE_TO_IDX["01"], CODE_TO_IDX["02"]],
        [CODE_TO_IDX["09"], CODE_TO_IDX["62"]],
    ], dtype=np.int8)
    idx_B = np.array([
        [CODE_TO_IDX["01"], CODE_TO_IDX["07"]],
        [CODE_TO_IDX["62"], CODE_TO_IDX["55"]],
    ], dtype=np.int8)
    logic = np.array([
        [0, 1],   # 单一多云, 阴转小雨
        [1, 3],   # 大雨转大雾, 大雾伴有轻度霾
    ], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)

    assert result[0, 0] == 101,   f"(0,0) 多云: {result[0,0]:05d}"
    assert result[0, 1] == 10207, f"(0,1) 阴转小雨: {result[0,1]:05d}"
    assert result[1, 0] == 10962, f"(1,0) 大雨转大雾: {result[1,0]:05d}"
    assert result[1, 1] == 36255, f"(1,1) 大雾伴有轻度霾: {result[1,1]:05d}"
    print("  [PASS] test_encode_batch: 2x2混合编码正确")


def test_encode_output_dtype():
    """编码输出应为int32"""
    idx_A = np.array([[0]], dtype=np.int8)
    idx_B = np.array([[0]], dtype=np.int8)
    logic = np.array([[0]], dtype=np.int8)
    result = encode(idx_A, idx_B, logic)
    assert result.dtype == np.int32, f"输出应为int32, 得到 {result.dtype}"
    print("  [PASS] test_encode_output_dtype: 输出为int32")


# ══════════════════════════════════════════════════════════
# 七、encode ↔ decode 往返一致性
# ══════════════════════════════════════════════════════════
def test_roundtrip():
    """encode后decode，验证信息一致"""
    test_cases = [
        (CODE_TO_IDX["02"], CODE_TO_IDX["07"], 1, "阴转小雨"),
        (CODE_TO_IDX["00"], CODE_TO_IDX["01"], 2, "晴间多云"),
        (CODE_TO_IDX["56"], CODE_TO_IDX["61"], 3, "中度霾伴有轻雾"),
    ]
    for a_idx, b_idx, k, expected_desc in test_cases:
        idx_A = np.array([[a_idx]], dtype=np.int8)
        idx_B = np.array([[b_idx]], dtype=np.int8)
        logic = np.array([[k]], dtype=np.int8)
        code_int = encode(idx_A, idx_B, logic)[0, 0]
        info = decode(int(code_int))
        assert info["预报表述"] == expected_desc, \
            f"往返验证失败: {code_int} → {info['预报表述']} != {expected_desc}"
    print("  [PASS] test_roundtrip: encode↔decode一致")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== 编码器模块单元测试 ===")
    # 单一
    test_encode_single_duoyun()
    test_encode_single_qing()
    test_encode_single_baoyu()
    # 转
    test_encode_zhuan()
    test_encode_zhuan_rain_to_snow()
    # 间
    test_encode_jian()
    test_encode_jian_yin_xiaoyu()
    # 伴有
    test_encode_accompany()
    # 解码
    test_decode_single()
    test_decode_zhuan()
    test_decode_jian()
    test_decode_accompany()
    # 批量
    test_encode_batch()
    test_encode_output_dtype()
    # 往返
    test_roundtrip()
    print("\n全部通过!")
