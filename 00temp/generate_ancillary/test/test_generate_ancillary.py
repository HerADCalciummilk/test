#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""generate_ancillary 当前辅助逻辑测试。"""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generate_ancillary.src.generate_ancillary import GenerateOrographyBandAncils


def test_coerce_threshold_bounds_rejects_wrong_number_of_bounds():
    """仅允许提供上下两个阈值。"""
    with pytest.raises(TypeError, match="上下两个界值"):
        GenerateOrographyBandAncils._coerce_threshold_bounds([0.0])

    with pytest.raises(TypeError, match="上下两个界值"):
        GenerateOrographyBandAncils._coerce_threshold_bounds([0.0, 50.0, 100.0])


def test_coerce_threshold_bounds_rejects_missing_bound():
    """阈值中存在空界值时会报错。"""
    with pytest.raises(TypeError, match="同时提供上下界"):
        GenerateOrographyBandAncils._coerce_threshold_bounds([None, 100.0])


def test_coerce_threshold_bounds_returns_float32_array():
    """合法输入会返回 float32 数组。"""
    result = GenerateOrographyBandAncils._coerce_threshold_bounds([0.0, 100.0])

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    np.testing.assert_allclose(result, np.array([0.0, 100.0], dtype=np.float32))


def test_broadcast_landmask_values_returns_input_when_shapes_match():
    """shape 一致时直接返回原始数组。"""
    landmask = np.ones((2, 3), dtype=np.int32)

    result = GenerateOrographyBandAncils._broadcast_landmask_values(landmask, (2, 3))
    assert result is landmask


def test_broadcast_landmask_values_broadcasts_to_target_shape():
    """shape 不一致但可广播时返回广播结果。"""
    landmask = np.array([[1, 0, 1]], dtype=np.int32)  # (1, 3)

    result = GenerateOrographyBandAncils._broadcast_landmask_values(landmask, (2, 3))

    assert result.shape == (2, 3)
    np.testing.assert_array_equal(result[0], np.array([1, 0, 1], dtype=np.int32))
    np.testing.assert_array_equal(result[1], np.array([1, 0, 1], dtype=np.int32))


def test_broadcast_landmask_values_raises_for_incompatible_shape():
    """shape 不可广播时抛出明确错误。"""
    landmask = np.ones((2, 2), dtype=np.int32)

    with pytest.raises(ValueError, match="海陆掩码形状无法广播到地形场"):
        GenerateOrographyBandAncils._broadcast_landmask_values(landmask, (2, 3))
