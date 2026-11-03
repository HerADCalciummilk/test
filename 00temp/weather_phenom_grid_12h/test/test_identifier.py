# -*- coding: utf-8 -*-
"""
单元测试 - 天气现象判识模块
验证 identify() 对各类天气现象的判识逻辑
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.identifier import identify, DIA_WeatherPhenomIdentifier
from resource.weather_config import (
    PTYPE_RAIN, PTYPE_SNOW, PTYPE_SLEET, PTYPE_FRZRAIN,
    WEATHER_INFLUENCE_LEVEL,
)

# 统一测试网格：4步 x 3lat x 4lon
N_STEPS, NLAT, NLON = 4, 3, 4
SHAPE = (NLAT, NLON)
FINE_SHAPE = (N_STEPS, NLAT, NLON)


def _zeros():
    """构造全零 [4, 3, 4] 数组"""
    return np.zeros(FINE_SHAPE, dtype=np.float32)


# ══════════════════════════════════════════════════════════
# 一、天空状况判识测试
# ══════════════════════════════════════════════════════════
def test_sky_qing():
    """TCC ≤ 30 → 晴(00)"""
    tcc = np.full(FINE_SHAPE, 20.0, dtype=np.float32)  # 全部 ≤ 30
    data = {"TCC": tcc}
    occur = identify(data)

    assert "00" in occur
    assert occur["00"]["12h"].all(), "TCC=20时所有格点应为晴"
    assert not occur["01"]["12h"].any(), "TCC=20时不应有多云"
    assert not occur["02"]["12h"].any(), "TCC=20时不应有阴"
    print("  [PASS] test_sky_qing: TCC=20→晴")


def test_sky_duoyun():
    """30 < TCC < 90 → 多云(01)"""
    tcc = np.full(FINE_SHAPE, 60.0, dtype=np.float32)
    data = {"TCC": tcc}
    occur = identify(data)

    assert occur["01"]["12h"].all(), "TCC=60时所有格点应为多云"
    assert not occur["00"]["12h"].any(), "TCC=60时不应有晴"
    print("  [PASS] test_sky_duoyun: TCC=60→多云")


def test_sky_yin():
    """TCC ≥ 90 → 阴(02)"""
    tcc = np.full(FINE_SHAPE, 95.0, dtype=np.float32)
    data = {"TCC": tcc}
    occur = identify(data)

    assert occur["02"]["12h"].all(), "TCC=95时所有格点应为阴"
    print("  [PASS] test_sky_yin: TCC=95→阴")


def test_sky_mixed():
    """前2步晴，后2步阴 → 12h内 晴+阴 都出现"""
    tcc = _zeros()
    tcc[:2] = 20.0   # 晴
    tcc[2:] = 95.0   # 阴
    data = {"TCC": tcc}
    occur = identify(data)

    assert occur["00"]["12h"].all(), "前2步TCC=20→晴应出现"
    assert occur["02"]["12h"].all(), "后2步TCC=95→阴应出现"
    # fine 精确检查
    assert occur["00"]["fine"][:2].all(), "前2步fine应为晴"
    assert not occur["00"]["fine"][2:].any(), "后2步fine不应为晴"
    print("  [PASS] test_sky_mixed: 混合天空状况")


def test_sky_fraction_unit():
    """TCC 以0~1表示时应自动×100"""
    tcc = np.full(FINE_SHAPE, 0.5, dtype=np.float32)  # 0.5 → 50%
    data = {"TCC": tcc}
    occur = identify(data)
    assert occur["01"]["12h"].all(), "TCC=0.5(50%)应识别为多云"
    print("  [PASS] test_sky_fraction_unit: 自动识别0~1单位")


# ══════════════════════════════════════════════════════════
# 二、降水现象判识测试
# ══════════════════════════════════════════════════════════
def test_rain_xiaoyu():
    """12h累积降雨 0.1~10mm → 小雨(07)"""
    r03 = _zeros()
    r03[0] = 2.0   # 第1步降水2mm
    r03[1] = 1.0   # 第2步降水1mm → 累积3mm
    ptype = np.full(FINE_SHAPE, PTYPE_RAIN, dtype=np.float32)
    data = {"R03": r03, "PTYPE03": ptype, "TCC": np.full(FINE_SHAPE, 50.0)}
    occur = identify(data)

    assert occur["07"]["12h"].all(), "累积3mm降雨应为小雨"
    assert not occur["08"]["12h"].any(), "3mm不应为中雨"
    print("  [PASS] test_rain_xiaoyu: 3mm→小雨")


def test_rain_zhongyu():
    """12h累积降雨 10~25mm → 中雨(08)"""
    r03 = _zeros()
    r03[0] = 5.0
    r03[1] = 5.0
    r03[2] = 5.0   # 累积15mm
    ptype = np.full(FINE_SHAPE, PTYPE_RAIN, dtype=np.float32)
    data = {"R03": r03, "PTYPE03": ptype, "TCC": np.full(FINE_SHAPE, 50.0)}
    occur = identify(data)

    assert occur["08"]["12h"].all(), "累积15mm降雨应为中雨"
    print("  [PASS] test_rain_zhongyu: 15mm→中雨")


def test_snow_xiaoxue():
    """12h累积降雪 0.1~2.5mm → 小雪(14)"""
    r03 = _zeros()
    r03[0] = 1.0   # 累积1mm
    ptype = np.full(FINE_SHAPE, PTYPE_SNOW, dtype=np.float32)
    data = {"R03": r03, "PTYPE03": ptype, "TCC": np.full(FINE_SHAPE, 50.0)}
    occur = identify(data)

    assert occur["14"]["12h"].all(), "累积1mm降雪应为小雪"
    print("  [PASS] test_snow_xiaoxue: 1mm→小雪")


def test_thunderstorm():
    """有降水且有雷暴 → 雷阵雨(04)"""
    r03 = _zeros()
    r03[0] = 5.0
    ptype = np.full(FINE_SHAPE, PTYPE_RAIN, dtype=np.float32)
    thunder = _zeros()
    thunder[0] = 1   # 第1步有雷暴
    data = {"R03": r03, "PTYPE03": ptype, "THUNDER": thunder,
            "TCC": np.full(FINE_SHAPE, 50.0)}
    occur = identify(data)

    assert occur["04"]["12h"].all(), "有降水+雷暴应为雷阵雨"
    print("  [PASS] test_thunderstorm: 雷阵雨")


def test_sleet():
    """相态为雨夹雪 → 雨夹雪(06)"""
    r03 = _zeros()
    r03[0] = 2.0
    ptype = np.full(FINE_SHAPE, PTYPE_SLEET, dtype=np.float32)
    data = {"R03": r03, "PTYPE03": ptype, "TCC": np.full(FINE_SHAPE, 50.0)}
    occur = identify(data)

    assert occur["06"]["12h"].all(), "相态雨夹雪应判识为雨夹雪"
    print("  [PASS] test_sleet: 雨夹雪")


# ══════════════════════════════════════════════════════════
# 三、视程障碍现象判识测试
# ══════════════════════════════════════════════════════════
def test_fog():
    """FOG等级2 → 大雾(62)"""
    fog = np.full(FINE_SHAPE, 2.0, dtype=np.float32)
    data = {"FOG": fog}
    occur = identify(data)

    assert occur["62"]["12h"].all(), "FOG=2应为大雾"
    assert not occur["61"]["12h"].any(), "FOG=2不应有轻雾"
    print("  [PASS] test_fog: FOG=2→大雾")


def test_haze():
    """HAZE等级3 → 重度霾(57)"""
    haze = np.full(FINE_SHAPE, 3.0, dtype=np.float32)
    data = {"HAZE": haze}
    occur = identify(data)

    assert occur["57"]["12h"].all(), "HAZE=3应为重度霾"
    print("  [PASS] test_haze: HAZE=3→重度霾")


def test_sand():
    """SAND等级2 → 沙尘暴(20)"""
    sand = np.full(FINE_SHAPE, 2.0, dtype=np.float32)
    data = {"SAND": sand}
    occur = identify(data)

    assert occur["20"]["12h"].all(), "SAND=2应为沙尘暴"
    print("  [PASS] test_sand: SAND=2→沙尘暴")


# ══════════════════════════════════════════════════════════
# 四、边界与补全测试
# ══════════════════════════════════════════════════════════
def test_empty_input():
    """空输入 → 返回空字典"""
    occur = identify({})
    assert occur == {}, "空输入应返回空字典"
    print("  [PASS] test_empty_input")


def test_all_codes_present():
    """正常输入后，31种天气现象都应有条目（不存在的填False）"""
    tcc = np.full(FINE_SHAPE, 50.0, dtype=np.float32)
    data = {"TCC": tcc}
    occur = identify(data)

    for code in WEATHER_INFLUENCE_LEVEL:
        assert code in occur, f"缺少电码 {code} 的条目"
        assert "12h" in occur[code], f"电码 {code} 缺少 12h 字段"
        assert "fine" in occur[code], f"电码 {code} 缺少 fine 字段"
    print("  [PASS] test_all_codes_present: 31种现象全有条目")


def test_fine_shape_correct():
    """fine 数组形状应为 [4, nlat, nlon]"""
    tcc = np.full(FINE_SHAPE, 50.0, dtype=np.float32)
    data = {"TCC": tcc}
    occur = identify(data)

    for code, v in occur.items():
        assert v["12h"].shape == SHAPE, f"{code} 12h shape 错误"
        assert v["fine"].shape == FINE_SHAPE, f"{code} fine shape 错误"
    print("  [PASS] test_fine_shape_correct")


# ══════════════════════════════════════════════════════════
# 五、Plugin 类接口测试
# ══════════════════════════════════════════════════════════
def test_plugin_class_interface():
    """DIA_WeatherPhenomIdentifier.process() 与 identify() 结果一致"""
    tcc = np.full(FINE_SHAPE, 60.0, dtype=np.float32)
    data = {"TCC": tcc}

    plugin = DIA_WeatherPhenomIdentifier()
    result_cls = plugin.process(data)
    result_fn  = identify(data)

    assert set(result_cls.keys()) == set(result_fn.keys()), "Plugin类与函数输出键集不一致"
    for code in result_cls:
        assert np.array_equal(result_cls[code]["12h"], result_fn[code]["12h"]), \
            f"{code} 12h 结果不一致"
    print("  [PASS] test_plugin_class_interface: Plugin类与函数输出一致")


def test_plugin_has_process_method():
    """Plugin 类必须有 process() 方法"""
    plugin = DIA_WeatherPhenomIdentifier()
    assert hasattr(plugin, "process"), "缺少 process() 方法"
    assert callable(plugin.process), "process 应为可调用方法"
    print("  [PASS] test_plugin_has_process_method")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== 天气现象判识模块单元测试 ===")
    # 天空状况
    test_sky_qing()
    test_sky_duoyun()
    test_sky_yin()
    test_sky_mixed()
    test_sky_fraction_unit()
    # 降水现象
    test_rain_xiaoyu()
    test_rain_zhongyu()
    test_snow_xiaoxue()
    test_thunderstorm()
    test_sleet()
    # 视程障碍
    test_fog()
    test_haze()
    test_sand()
    # 边界
    test_empty_input()
    test_all_codes_present()
    test_fine_shape_correct()
    print("\n全部通过!")
