# -*- coding: utf-8 -*-
"""
单元测试 - 数据加载模块
验证 get_segment_fh / load_segment 的正确性
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from unittest.mock import patch, MagicMock
from src.utils.data_loader import load_segment
from resource.data_schema import get_segment_fh
from resource.data_schema import VARS_240H, VARS_72H


# ══════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════
def _make_da(shape2d=(3, 4)):
    """构造 meteva 风格 6D DataArray (用 xarray)"""
    import xarray as xr
    lat = np.linspace(30.0, 30.0 + shape2d[0] - 1, shape2d[0], dtype=np.float32)
    lon = np.linspace(110.0, 110.0 + shape2d[1] - 1, shape2d[1], dtype=np.float32)
    data = np.ones((1, 1, 1, 1, *shape2d), dtype=np.float32)
    return xr.DataArray(
        data,
        coords={"member": ["d"], "level": [0.], "time": [0], "dtime": [3],
                "lat": lat, "lon": lon},
        dims=["member", "level", "time", "dtime", "lat", "lon"]
    )


# ══════════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════════
def test_segment_fh_seg1():
    """seg_idx=1 → FH [3, 6, 9, 12]"""
    assert get_segment_fh(1) == [3, 6, 9, 12]
    print("  [PASS] test_segment_fh_seg1")


def test_segment_fh_seg7():
    """seg_idx=7 → FH [75, 78, 81, 84]"""
    assert get_segment_fh(7) == [75, 78, 81, 84]
    print("  [PASS] test_segment_fh_seg7")


def test_segment_fh_seg20():
    """seg_idx=20 → FH [231, 234, 237, 240]"""
    assert get_segment_fh(20) == [231, 234, 237, 240]
    print("  [PASS] test_segment_fh_seg20")


def test_segment_fh_boundary():
    """seg_idx=6 → FH [63, 66, 69, 72]（72h变量边界段）"""
    fh = get_segment_fh(6)
    assert fh == [63, 66, 69, 72]
    assert fh[-1] == 72, "seg6最后一个时效应为72"
    print("  [PASS] test_segment_fh_boundary")


def test_load_segment_basic():
    """加载seg=1，mock返回全1数组，验证输出shape和类型"""
    S = (3, 4)

    from src.utils import data_loader
    with patch.object(data_loader, "_read_one") as mock_read:
        mock_read.return_value = (
            np.ones(S, dtype=np.float32),
            np.linspace(30, 32, S[0]),
            np.linspace(110, 113, S[1])
        )
        dd, shape, lat, lon = load_segment("2026030100", 1)

    assert shape == S, f"期望 shape={S}, 得到 {shape}"
    # 所有变量应存在且 shape=(4, 3, 4)
    for var in VARS_240H + VARS_72H:
        assert var in dd, f"缺少变量 {var}"
        assert dd[var].shape == (4, *S), f"{var} shape异常: {dd[var].shape}"
    print("  [PASS] test_load_segment_basic")


def test_load_segment_72h_fill_zero():
    """seg=7 超出72h，72h变量应全填0"""
    S = (3, 4)

    from src.utils import data_loader
    with patch.object(data_loader, "_read_one") as mock_read:
        def _mock(var, init, fh):
            if var in VARS_72H and fh > 72:
                return (None, None, None)
            return (
                np.ones(S, dtype=np.float32),
                np.linspace(30, 32, S[0]),
                np.linspace(110, 113, S[1])
            )
        mock_read.side_effect = _mock
        dd, shape, lat, lon = load_segment("2026030100", 7)

    # 72h变量全部时步都超过72h → 全0
    for var in VARS_72H:
        assert np.all(dd[var] == 0), f"{var} 应全零但不是"
    print("  [PASS] test_load_segment_72h_fill_zero")


def test_load_segment_all_missing():
    """所有文件缺失 → shape=None"""
    from src.utils import data_loader
    with patch.object(data_loader, "_read_one", return_value=(None, None, None)):
        dd, shape, lat, lon = load_segment("2026030100", 1)

    assert shape is None, "全缺失时shape应为None"
    print("  [PASS] test_load_segment_all_missing")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=== 数据加载模块单元测试 ===")
    test_segment_fh_seg1()
    test_segment_fh_seg7()
    test_segment_fh_seg20()
    test_segment_fh_boundary()
    test_load_segment_basic()
    test_load_segment_72h_fill_zero()
    test_load_segment_all_missing()
    print("\n全部通过!")
